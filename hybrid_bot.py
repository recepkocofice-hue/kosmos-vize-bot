#!/usr/bin/env python3
"""
Kosmos Visa Hybrid Bot

Combines fast API monitoring with reliable browser-based booking.

Architecture:
- Phase 1: Fast API polling for slot availability (curl_cffi)
- Phase 2: Instant Telegram notifications
- Phase 3: Browser automation for booking (Playwright)
- Phase 4: Confirmation and state persistence

Usage:
    python hybrid_bot.py                    # Monitor only
    python hybrid_bot.py --auto-book        # Monitor + auto-book
    python hybrid_bot.py --headless         # Run browser in background
"""

import os
import sys
import json
import asyncio
import logging
import argparse
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Set
from enum import Enum
from pathlib import Path
import signal

# Third-party imports
from curl_cffi import requests as curl_requests
from dotenv import load_dotenv

# Playwright (optional - only for booking)
try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

class ApplicationType(Enum):
    INDIVIDUAL = 1
    FAMILY = 2


class AppointmentType(Enum):
    STANDARD = 16
    VIP = 18
    EEA_AB_SPOUSE = 2339


@dataclass
class Applicant:
    """Applicant information for booking"""
    first_name: str
    last_name: str
    nationality_number: str
    passport_number: str
    birth_date: str
    email: str
    phone: str

    @classmethod
    def from_env(cls) -> 'Applicant':
        return cls(
            first_name=os.getenv('APPLICANT_FIRST_NAME', ''),
            last_name=os.getenv('APPLICANT_LAST_NAME', ''),
            nationality_number=os.getenv('APPLICANT_NATIONALITY_NUMBER', ''),
            passport_number=os.getenv('APPLICANT_PASSPORT_NUMBER', ''),
            birth_date=os.getenv('APPLICANT_BIRTH_DATE', ''),
            email=os.getenv('APPLICANT_EMAIL', ''),
            phone=os.getenv('APPLICANT_PHONE', '')
        )

    def is_valid(self) -> bool:
        required = [self.first_name, self.last_name, self.nationality_number, self.email, self.phone]
        return all(required)


@dataclass
class BotConfig:
    """Bot configuration"""
    # Appointment settings
    dealer_id: int = 1
    application_type: ApplicationType = ApplicationType.INDIVIDUAL
    appointment_type: AppointmentType = AppointmentType.STANDARD

    # Monitoring settings
    check_interval: int = 60  # seconds
    days_to_check: int = 30
    min_quota: int = 1  # Minimum available slots to trigger

    # Filtering
    preferred_dates: List[str] = field(default_factory=list)  # ["2026/01/15", "2026/01/16"]
    preferred_times: List[str] = field(default_factory=list)  # ["09:00-12:00", "14:00-17:00"]
    excluded_dates: List[str] = field(default_factory=list)   # Dates to skip

    # Booking settings
    auto_book: bool = False
    headless: bool = False
    booking_timeout: int = 120  # seconds for CAPTCHA solving

    # Telegram
    telegram_token: str = ''
    telegram_chat_id: str = ''

    # Persistence
    db_path: str = 'bot_state.db'
    screenshot_dir: str = 'screenshots'

    @classmethod
    def from_env(cls) -> 'BotConfig':
        return cls(
            dealer_id=int(os.getenv('DEALER_ID', '1')),
            application_type=ApplicationType(int(os.getenv('APPLICATION_TYPE', '1'))),
            appointment_type=AppointmentType(int(os.getenv('APPOINTMENT_TYPE', '16'))),
            check_interval=int(os.getenv('CHECK_INTERVAL', '60')),
            days_to_check=int(os.getenv('DAYS_TO_CHECK', '30')),
            min_quota=int(os.getenv('MIN_QUOTA', '1')),
            preferred_dates=_parse_list(os.getenv('PREFERRED_DATES', '')),
            preferred_times=_parse_list(os.getenv('PREFERRED_TIMES', '')),
            excluded_dates=_parse_list(os.getenv('EXCLUDED_DATES', '')),
            auto_book=os.getenv('AUTO_BOOK', 'false').lower() == 'true',
            headless=os.getenv('HEADLESS', 'false').lower() == 'true',
            telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
        )


def _parse_list(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging with file and console output"""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # File handler
    file_handler = logging.FileHandler('hybrid_bot.log')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Configure root logger
    logger = logging.getLogger('KosmosBot')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# ============================================================================
# STATE PERSISTENCE
# ============================================================================

class StateManager:
    """Manages bot state with SQLite persistence"""

    def __init__(self, db_path: str = 'bot_state.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS notified_slots (
                    slot_key TEXT PRIMARY KEY,
                    date TEXT,
                    time TEXT,
                    quota INTEGER,
                    notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS booking_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_key TEXT,
                    status TEXT,
                    error_message TEXT,
                    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS successful_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_key TEXT,
                    confirmation_id TEXT,
                    screenshot_path TEXT,
                    booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def is_slot_notified(self, slot_key: str) -> bool:
        """Check if we've already notified about this slot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM notified_slots WHERE slot_key = ?',
                (slot_key,)
            )
            return cursor.fetchone() is not None

    def mark_slot_notified(self, slot_key: str, date: str, time: str, quota: int):
        """Mark a slot as notified"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO notified_slots (slot_key, date, time, quota) VALUES (?, ?, ?, ?)',
                (slot_key, date, time, quota)
            )
            conn.commit()

    def log_booking_attempt(self, slot_key: str, status: str, error: str = None):
        """Log a booking attempt"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT INTO booking_attempts (slot_key, status, error_message) VALUES (?, ?, ?)',
                (slot_key, status, error)
            )
            conn.commit()

    def log_successful_booking(self, slot_key: str, confirmation_id: str, screenshot_path: str):
        """Log a successful booking"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT INTO successful_bookings (slot_key, confirmation_id, screenshot_path) VALUES (?, ?, ?)',
                (slot_key, confirmation_id, screenshot_path)
            )
            conn.commit()

    def has_successful_booking(self) -> bool:
        """Check if we've already made a successful booking"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT 1 FROM successful_bookings LIMIT 1')
            return cursor.fetchone() is not None

    def cleanup_old_slots(self, hours: int = 24):
        """Remove old notified slots"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'DELETE FROM notified_slots WHERE notified_at < datetime("now", ?)',
                (f'-{hours} hours',)
            )
            conn.commit()


# ============================================================================
# SLOT MONITOR (API-based)
# ============================================================================

@dataclass
class Slot:
    """Represents an available appointment slot"""
    date: str
    time: str
    slot_id: str
    quota: int
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.date}_{self.time}"

    def __str__(self) -> str:
        return f"Slot({self.date} {self.time}, quota={self.quota})"


class SlotMonitor:
    """Fast API-based slot monitoring"""

    API_URL = "https://api.kosmosvize.com.tr/api/AppointmentLayouts/GetAppointmentHourQoutaInfo"

    HEADERS = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9,tr;q=0.8',
        'origin': 'https://basvuru.kosmosvize.com.tr',
        'referer': 'https://basvuru.kosmosvize.com.tr/',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }

    def __init__(self, config: BotConfig, applicant: Applicant, logger: logging.Logger):
        self.config = config
        self.applicant = applicant
        self.logger = logger

    async def check_date(self, date: str) -> List[Slot]:
        """Check availability for a single date"""
        params = {
            'nationalityNumber': self.applicant.nationality_number,
            'dealerId': self.config.dealer_id,
            'date': date,
            'appointmentTypeId': self.config.appointment_type.value,
            'onlyAvailable': 'true',
            'applicationType': self.config.application_type.value
        }

        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: curl_requests.get(
                    self.API_URL,
                    headers=self.HEADERS,
                    params=params,
                    impersonate="chrome",
                    timeout=10
                )
            )

            if response.status_code != 200:
                self.logger.warning(f"API returned {response.status_code} for {date}")
                return []

            data = response.json()

            if not isinstance(data, list):
                return []

            slots = []
            for item in data:
                # Parse slot data (field names may vary)
                quota = item.get('quota', item.get('availableCount', item.get('count', 0)))

                if quota >= self.config.min_quota:
                    slot = Slot(
                        date=date,
                        time=item.get('hour', item.get('time', item.get('startTime', ''))),
                        slot_id=str(item.get('id', item.get('slotId', item.get('layoutId', '')))),
                        quota=quota,
                        raw_data=item
                    )
                    slots.append(slot)

            return slots

        except Exception as e:
            self.logger.error(f"Error checking {date}: {e}")
            return []

    async def scan_all_dates(self) -> List[Slot]:
        """Scan all dates in parallel"""
        dates = []
        for i in range(self.config.days_to_check):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y/%m/%d")

            # Skip excluded dates
            if date in self.config.excluded_dates:
                continue

            # If preferred dates specified, only check those
            if self.config.preferred_dates and date not in self.config.preferred_dates:
                continue

            dates.append(date)

        self.logger.info(f"Scanning {len(dates)} dates...")

        # Parallel scanning with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def limited_check(date: str) -> List[Slot]:
            async with semaphore:
                slots = await self.check_date(date)
                await asyncio.sleep(0.1)  # Small delay between requests
                return slots

        tasks = [limited_check(date) for date in dates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_slots = []
        for result in results:
            if isinstance(result, list):
                all_slots.extend(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Scan error: {result}")

        # Filter by preferred times
        if self.config.preferred_times:
            all_slots = self._filter_by_time(all_slots)

        return all_slots

    def _filter_by_time(self, slots: List[Slot]) -> List[Slot]:
        """Filter slots by preferred time ranges"""
        filtered = []
        for slot in slots:
            for time_range in self.config.preferred_times:
                if '-' in time_range:
                    start, end = time_range.split('-')
                    if start.strip() <= slot.time <= end.strip():
                        filtered.append(slot)
                        break
        return filtered


# ============================================================================
# TELEGRAM NOTIFIER
# ============================================================================

class TelegramNotifier:
    """Sends notifications via Telegram"""

    BOOKING_URL = "https://basvuru.kosmosvize.com.tr"

    def __init__(self, token: str, chat_id: str, logger: logging.Logger):
        self.token = token
        self.chat_id = chat_id
        self.logger = logger
        self.enabled = bool(token and chat_id)

        if not self.enabled:
            self.logger.warning("Telegram not configured - notifications will be logged only")

    def send(self, message: str, parse_mode: str = 'HTML'):
        """Send a message"""
        if not self.enabled:
            self.logger.info(f"[NOTIFICATION] {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False
            }
            response = curl_requests.post(url, json=data, timeout=10)

            if response.status_code != 200:
                self.logger.error(f"Telegram API error: {response.text}")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")

    def notify_slot_available(self, slot: Slot):
        """Send slot availability notification"""
        message = (
            f"🎫 <b>APPOINTMENT AVAILABLE!</b>\n\n"
            f"📅 Date: <b>{slot.date}</b>\n"
            f"🕐 Time: <b>{slot.time}</b>\n"
            f"👥 Quota: <b>{slot.quota}</b>\n\n"
            f"🔗 <a href='{self.BOOKING_URL}'>Book Now</a>"
        )
        self.send(message)

    def notify_booking_started(self, slot: Slot):
        """Notify that auto-booking has started"""
        message = (
            f"🤖 <b>AUTO-BOOKING STARTED</b>\n\n"
            f"Attempting to book:\n"
            f"📅 {slot.date} at {slot.time}\n\n"
            f"⏳ Please wait..."
        )
        self.send(message)

    def notify_captcha_required(self):
        """Notify that CAPTCHA needs manual solving"""
        message = (
            f"⚠️ <b>CAPTCHA DETECTED!</b>\n\n"
            f"Please solve the CAPTCHA manually.\n"
            f"The browser window should be visible.\n\n"
            f"⏱ Waiting up to 2 minutes..."
        )
        self.send(message)

    def notify_booking_success(self, slot: Slot, confirmation_id: str):
        """Notify successful booking"""
        message = (
            f"✅ <b>BOOKING SUCCESSFUL!</b>\n\n"
            f"📅 Date: <b>{slot.date}</b>\n"
            f"🕐 Time: <b>{slot.time}</b>\n"
            f"🎫 Confirmation: <b>{confirmation_id}</b>\n\n"
            f"📧 Check your email for details."
        )
        self.send(message)

    def notify_booking_failed(self, slot: Slot, error: str):
        """Notify failed booking"""
        message = (
            f"❌ <b>BOOKING FAILED</b>\n\n"
            f"📅 Slot: {slot.date} at {slot.time}\n"
            f"⚠️ Error: {error}\n\n"
            f"🔗 Try manually: {self.BOOKING_URL}"
        )
        self.send(message)

    def notify_bot_started(self, config: BotConfig):
        """Notify that bot has started"""
        message = (
            f"🚀 <b>Bot Started</b>\n\n"
            f"📍 Dealer: {config.dealer_id}\n"
            f"📋 Type: {config.appointment_type.name}\n"
            f"⏱ Check interval: {config.check_interval}s\n"
            f"📅 Scanning: {config.days_to_check} days\n"
            f"🤖 Auto-book: {'Yes' if config.auto_book else 'No'}"
        )
        self.send(message)


# ============================================================================
# BROWSER BOOKER (Playwright-based)
# ============================================================================

class BrowserBooker:
    """Browser automation for booking"""

    BOOKING_URL = "https://basvuru.kosmosvize.com.tr"

    def __init__(
        self,
        config: BotConfig,
        applicant: Applicant,
        notifier: TelegramNotifier,
        state: StateManager,
        logger: logging.Logger
    ):
        self.config = config
        self.applicant = applicant
        self.notifier = notifier
        self.state = state
        self.logger = logger

        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    async def setup(self):
        """Initialize browser with stealth settings"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not installed. Run:\n"
                "pip install playwright && playwright install chromium"
            )

        self.logger.info("Launching browser...")

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )

        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='tr-TR',
            timezone_id='Europe/Istanbul',
            permissions=['geolocation'],
            geolocation={'latitude': 41.0082, 'longitude': 28.9784},  # Istanbul
        )

        # Stealth scripts
        await self.context.add_init_script("""
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5].map(() => ({ length: 1 }))
            });

            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['tr-TR', 'tr', 'en-US', 'en']
            });

            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(30000)

        # Create screenshot directory
        Path(self.config.screenshot_dir).mkdir(exist_ok=True)

        self.logger.info("Browser ready")

    async def close(self):
        """Clean up browser resources"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.logger.info("Browser closed")

    async def book_slot(self, slot: Slot) -> bool:
        """
        Attempt to book a slot

        Returns True if successful, False otherwise.
        """
        self.logger.info(f"Starting booking for {slot}")
        self.notifier.notify_booking_started(slot)
        self.state.log_booking_attempt(slot.key, 'started')

        try:
            # Navigate to booking page
            await self._navigate_to_booking()

            # Select appointment options
            await self._select_options(slot)

            # Fill applicant form
            await self._fill_form()

            # Handle CAPTCHA if present
            captcha_solved = await self._handle_captcha()
            if not captcha_solved:
                raise Exception("CAPTCHA not solved in time")

            # Submit booking
            confirmation_id = await self._submit_booking()

            if confirmation_id:
                # Success!
                screenshot_path = await self._take_screenshot('confirmation')
                self.state.log_successful_booking(slot.key, confirmation_id, screenshot_path)
                self.notifier.notify_booking_success(slot, confirmation_id)
                self.logger.info(f"Booking successful! Confirmation: {confirmation_id}")
                return True
            else:
                raise Exception("No confirmation received")

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Booking failed: {error_msg}")
            self.state.log_booking_attempt(slot.key, 'failed', error_msg)
            self.notifier.notify_booking_failed(slot, error_msg)
            await self._take_screenshot('error')
            return False

    async def _navigate_to_booking(self):
        """Navigate to booking portal"""
        self.logger.info(f"Navigating to {self.BOOKING_URL}")
        await self.page.goto(self.BOOKING_URL, wait_until='networkidle')
        await self.page.wait_for_load_state('domcontentloaded')
        await asyncio.sleep(1)  # Let JavaScript initialize

    async def _select_options(self, slot: Slot):
        """Select appointment type, date, and time"""
        self.logger.info("Selecting appointment options...")

        # These selectors need to be discovered from the actual website
        # Using multiple possible selectors for robustness

        selectors = {
            'dealer': ['select[name="dealer"]', '#dealerId', '[data-field="dealer"]'],
            'app_type': ['select[name="applicationType"]', '#applicationType'],
            'apt_type': ['select[name="appointmentType"]', '#appointmentType'],
            'date': ['input[name="date"]', '#appointmentDate', '.date-picker'],
            'time': [f'[data-time="{slot.time}"]', f'button:has-text("{slot.time}")']
        }

        # Try to select dealer
        for selector in selectors['dealer']:
            try:
                if await self.page.locator(selector).count() > 0:
                    await self.page.select_option(selector, str(self.config.dealer_id))
                    break
            except:
                pass

        # Try to select application type
        for selector in selectors['app_type']:
            try:
                if await self.page.locator(selector).count() > 0:
                    await self.page.select_option(selector, str(self.config.application_type.value))
                    break
            except:
                pass

        # Try to select appointment type
        for selector in selectors['apt_type']:
            try:
                if await self.page.locator(selector).count() > 0:
                    await self.page.select_option(selector, str(self.config.appointment_type.value))
                    break
            except:
                pass

        await asyncio.sleep(1)  # Wait for form updates

    async def _fill_form(self):
        """Fill in applicant information"""
        self.logger.info("Filling applicant form...")

        # Map of possible selectors to values
        field_mapping = [
            (['input[name="firstName"]', '#firstName', '[data-field="firstName"]'],
             self.applicant.first_name),
            (['input[name="lastName"]', '#lastName', '[data-field="lastName"]'],
             self.applicant.last_name),
            (['input[name="nationalityNumber"]', '#tcKimlik', '#nationalityNumber'],
             self.applicant.nationality_number),
            (['input[name="passportNumber"]', '#passport', '#passportNumber'],
             self.applicant.passport_number),
            (['input[name="email"]', '#email', '[type="email"]'],
             self.applicant.email),
            (['input[name="phone"]', '#phone', '[type="tel"]'],
             self.applicant.phone),
            (['input[name="birthDate"]', '#birthDate', '[data-field="birthDate"]'],
             self.applicant.birth_date),
        ]

        for selectors, value in field_mapping:
            if not value:
                continue
            for selector in selectors:
                try:
                    element = self.page.locator(selector).first
                    if await element.count() > 0:
                        await element.fill(value)
                        await asyncio.sleep(0.1)
                        break
                except:
                    pass

        self.logger.info("Form filled")

    async def _handle_captcha(self) -> bool:
        """Detect and handle CAPTCHA"""
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            '.g-recaptcha',
            '.h-captcha',
            '#captcha'
        ]

        captcha_found = False
        for selector in captcha_selectors:
            if await self.page.locator(selector).count() > 0:
                captcha_found = True
                break

        if not captcha_found:
            self.logger.info("No CAPTCHA detected")
            return True

        self.logger.warning("CAPTCHA detected - waiting for manual solving")
        self.notifier.notify_captcha_required()

        # Wait for CAPTCHA to be solved
        try:
            # Look for success indicators or form submission becoming available
            await self.page.wait_for_function(
                '''() => {
                    // Check for reCAPTCHA success
                    const recaptcha = document.querySelector('.recaptcha-checkbox-checked');
                    if (recaptcha) return true;

                    // Check for hCaptcha success
                    const hcaptcha = document.querySelector('[data-hcaptcha-response]:not([data-hcaptcha-response=""])');
                    if (hcaptcha) return true;

                    // Check if submit button is now enabled
                    const submit = document.querySelector('button[type="submit"]:not([disabled])');
                    if (submit) return true;

                    return false;
                }''',
                timeout=self.config.booking_timeout * 1000
            )
            self.logger.info("CAPTCHA solved!")
            return True
        except:
            self.logger.error("CAPTCHA solving timeout")
            return False

    async def _submit_booking(self) -> Optional[str]:
        """Submit the booking form and return confirmation ID"""
        self.logger.info("Submitting booking...")

        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Randevu Al")',
            'button:has-text("Book")',
            'button:has-text("Onayla")',
            'button:has-text("Submit")',
            '.submit-btn',
            '#submitButton'
        ]

        # Click submit button
        for selector in submit_selectors:
            try:
                button = self.page.locator(selector).first
                if await button.count() > 0:
                    await button.click()
                    self.logger.info("Submit clicked")
                    break
            except:
                pass

        # Wait for response
        await asyncio.sleep(3)

        # Check for confirmation
        confirmation_id = await self._extract_confirmation()

        return confirmation_id

    async def _extract_confirmation(self) -> Optional[str]:
        """Try to extract confirmation ID from the page"""
        # Look for confirmation elements
        confirmation_selectors = [
            '.confirmation-number',
            '.booking-id',
            '#confirmationId',
            '[data-confirmation]'
        ]

        for selector in confirmation_selectors:
            try:
                element = self.page.locator(selector).first
                if await element.count() > 0:
                    text = await element.text_content()
                    if text:
                        return text.strip()
            except:
                pass

        # Check URL for confirmation
        url = self.page.url
        if 'confirm' in url.lower() or 'success' in url.lower():
            return f"URL:{url}"

        # Check page content for success indicators
        content = await self.page.content()
        success_keywords = ['başarılı', 'successful', 'confirmation', 'onay']
        for keyword in success_keywords:
            if keyword.lower() in content.lower():
                return f"PAGE_SUCCESS_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return None

    async def _take_screenshot(self, name: str) -> str:
        """Take a screenshot and return the path"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}.png"
        path = Path(self.config.screenshot_dir) / filename
        await self.page.screenshot(path=str(path), full_page=True)
        self.logger.info(f"Screenshot saved: {path}")
        return str(path)


# ============================================================================
# HYBRID BOT (Main Orchestrator)
# ============================================================================

class HybridBot:
    """
    Main bot that orchestrates monitoring and booking

    Flow:
    1. Monitor for slots using fast API calls
    2. Send Telegram notification when slot found
    3. If auto_book enabled, use browser to complete booking
    4. Persist state to survive restarts
    """

    def __init__(
        self,
        config: BotConfig,
        applicant: Applicant,
        verbose: bool = False
    ):
        self.config = config
        self.applicant = applicant
        self.logger = setup_logging(verbose)

        # Initialize components
        self.state = StateManager(config.db_path)
        self.notifier = TelegramNotifier(
            config.telegram_token,
            config.telegram_chat_id,
            self.logger
        )
        self.monitor = SlotMonitor(config, applicant, self.logger)
        self.booker: Optional[BrowserBooker] = None

        # Running state
        self.running = False
        self.booking_in_progress = False

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(sig, frame):
            self.logger.info("Shutdown requested...")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def run(self):
        """Main bot loop"""
        self._setup_signal_handlers()
        self.running = True

        # Print startup banner
        self._print_banner()

        # Check if we already have a booking
        if self.state.has_successful_booking():
            self.logger.warning("A successful booking already exists! Clear bot_state.db to restart.")
            return

        # Validate configuration
        if not self.applicant.is_valid():
            self.logger.error("Applicant information incomplete! Check .env file.")
            return

        # Notify start
        self.notifier.notify_bot_started(self.config)

        # Cleanup old notified slots
        self.state.cleanup_old_slots(24)

        try:
            while self.running:
                await self._check_and_book()

                if self.running:
                    self.logger.info(f"Next check in {self.config.check_interval}s...")
                    await asyncio.sleep(self.config.check_interval)

        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            raise
        finally:
            if self.booker:
                await self.booker.close()
            self.logger.info("Bot stopped")

    async def _check_and_book(self):
        """Single check and booking cycle"""
        try:
            # Scan for slots
            slots = await self.monitor.scan_all_dates()

            if not slots:
                self.logger.info("No available slots")
                return

            self.logger.info(f"Found {len(slots)} available slot(s)!")

            for slot in slots:
                # Skip already notified
                if self.state.is_slot_notified(slot.key):
                    self.logger.debug(f"Already notified: {slot.key}")
                    continue

                # Mark as notified
                self.state.mark_slot_notified(slot.key, slot.date, slot.time, slot.quota)

                # Send notification
                self.notifier.notify_slot_available(slot)
                self.logger.info(f"Notified: {slot}")

                # Auto-book if enabled
                if self.config.auto_book and not self.booking_in_progress:
                    self.booking_in_progress = True

                    try:
                        success = await self._attempt_booking(slot)

                        if success:
                            self.logger.info("Booking successful! Stopping bot.")
                            self.running = False
                            return
                    finally:
                        self.booking_in_progress = False

        except Exception as e:
            self.logger.error(f"Check cycle error: {e}")

    async def _attempt_booking(self, slot: Slot) -> bool:
        """Attempt to book a slot using browser automation"""
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.error("Playwright not available for booking")
            return False

        # Initialize browser if needed
        if not self.booker:
            self.booker = BrowserBooker(
                self.config,
                self.applicant,
                self.notifier,
                self.state,
                self.logger
            )
            await self.booker.setup()

        return await self.booker.book_slot(slot)

    def _print_banner(self):
        """Print startup banner"""
        banner = """
╔═══════════════════════════════════════════════════════════════╗
║              KOSMOS VISA HYBRID BOT                           ║
║                                                               ║
║  Fast API monitoring + Reliable browser booking               ║
╚═══════════════════════════════════════════════════════════════╝
"""
        print(banner)
        self.logger.info("=" * 60)
        self.logger.info(f"Dealer ID: {self.config.dealer_id}")
        self.logger.info(f"Application Type: {self.config.application_type.name}")
        self.logger.info(f"Appointment Type: {self.config.appointment_type.name}")
        self.logger.info(f"Check Interval: {self.config.check_interval}s")
        self.logger.info(f"Days to Check: {self.config.days_to_check}")
        self.logger.info(f"Auto-book: {self.config.auto_book}")
        self.logger.info(f"Headless: {self.config.headless}")
        self.logger.info("=" * 60)


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Kosmos Visa Appointment Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hybrid_bot.py                    # Monitor only
  python hybrid_bot.py --auto-book        # Monitor + auto-book
  python hybrid_bot.py --headless         # Run browser hidden
  python hybrid_bot.py -i 30              # Check every 30 seconds
        """
    )

    parser.add_argument(
        '--auto-book', '-a',
        action='store_true',
        help='Enable automatic booking when slots found'
    )

    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )

    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=None,
        help='Check interval in seconds (default: 60)'
    )

    parser.add_argument(
        '--days', '-d',
        type=int,
        default=None,
        help='Number of days to check (default: 30)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


async def main():
    """Entry point"""
    args = parse_args()

    # Load configuration
    config = BotConfig.from_env()
    applicant = Applicant.from_env()

    # Override with CLI arguments
    if args.auto_book:
        config.auto_book = True
    if args.headless:
        config.headless = True
    if args.interval:
        config.check_interval = args.interval
    if args.days:
        config.days_to_check = args.days

    # Create and run bot
    bot = HybridBot(config, applicant, verbose=args.verbose)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
