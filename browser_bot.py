"""
Kosmos Visa Browser Automation Bot (Theoretical/Educational)

This version uses browser automation (Playwright) to interact with
the booking portal like a real user would.

EDUCATIONAL PURPOSE ONLY - Demonstrates browser automation concepts.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")

from curl_cffi import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('browser_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ApplicationType(Enum):
    INDIVIDUAL = 1
    FAMILY = 2


class AppointmentTypeId(Enum):
    STANDARD = 16
    VIP = 18
    EEA_AB_SPOUSE = 2339


@dataclass
class ApplicantInfo:
    """Applicant information for the booking form"""
    first_name: str
    last_name: str
    nationality_number: str
    passport_number: str
    birth_date: str
    email: str
    phone: str
    address: str = ""


@dataclass
class BookingConfig:
    """Bot configuration"""
    dealer_id: int = 1
    application_type: ApplicationType = ApplicationType.INDIVIDUAL
    appointment_type: AppointmentTypeId = AppointmentTypeId.STANDARD
    check_interval: int = 60
    days_to_check: int = 30
    headless: bool = False  # Set to True for background operation
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class KosmosBrowserBot:
    """
    Browser automation bot for Kosmos Visa appointments

    This uses Playwright to control a real browser, which:
    - Bypasses most anti-bot detection
    - Handles JavaScript-rendered content
    - Can fill forms like a human
    - Supports CAPTCHA solving (manual or service)
    """

    BOOKING_URL = "https://basvuru.kosmosvize.com.tr"
    API_URL = "https://api.kosmosvize.com.tr/api"

    def __init__(self, applicant: ApplicantInfo, config: BookingConfig):
        self.applicant = applicant
        self.config = config
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.notified_slots: set = set()

    async def setup_browser(self):
        """Initialize the browser with anti-detection settings"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed")

        logger.info("Setting up browser...")

        playwright = await async_playwright().start()

        # Launch browser with stealth settings
        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
        )

        # Create context with realistic viewport and user agent
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='tr-TR',
            timezone_id='Europe/Istanbul',
        )

        # Add stealth scripts to avoid detection
        await self.context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['tr-TR', 'tr', 'en-US', 'en']
            });
        """)

        self.page = await self.context.new_page()

        # Set default timeout
        self.page.set_default_timeout(30000)

        logger.info("Browser setup complete")

    async def close_browser(self):
        """Clean up browser resources"""
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")

    async def check_availability_api(self, date: str) -> List[dict]:
        """
        Check availability using the API (faster than browser)
        Uses curl_cffi for browser impersonation
        """
        url = f"{self.API_URL}/AppointmentLayouts/GetAppointmentHourQoutaInfo"

        params = {
            'nationalityNumber': self.applicant.nationality_number,
            'dealerId': self.config.dealer_id,
            'date': date,
            'appointmentTypeId': self.config.appointment_type.value,
            'onlyAvailable': 'true',
            'applicationType': self.config.application_type.value
        }

        headers = {
            'accept': 'application/json',
            'origin': 'https://basvuru.kosmosvize.com.tr',
            'referer': 'https://basvuru.kosmosvize.com.tr/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            response = requests.get(url, headers=headers, params=params, impersonate="chrome")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            logger.error(f"API check failed for {date}: {e}")

        return []

    async def scan_for_slots(self) -> List[dict]:
        """Scan multiple days for available slots"""
        all_slots = []

        for i in range(self.config.days_to_check):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y/%m/%d")
            slots = await self.check_availability_api(date)

            for slot in slots:
                slot['date'] = date
                all_slots.append(slot)

            if slots:
                logger.info(f"Found {len(slots)} slots on {date}")

            await asyncio.sleep(0.3)  # Rate limiting

        return all_slots

    async def navigate_to_booking(self):
        """Navigate to the booking portal"""
        logger.info(f"Navigating to {self.BOOKING_URL}")

        await self.page.goto(self.BOOKING_URL, wait_until='networkidle')

        # Wait for page to fully load
        await self.page.wait_for_load_state('domcontentloaded')

        # Take screenshot for debugging
        await self.page.screenshot(path='screenshots/booking_page.png')

        logger.info("Booking page loaded")

    async def select_appointment_type(self):
        """
        Select the appointment type on the booking form

        Note: Selectors are THEORETICAL and would need to be
        discovered by inspecting the actual website.
        """
        logger.info("Selecting appointment type...")

        # These selectors are examples - real ones need inspection
        theoretical_selectors = {
            'appointment_type_dropdown': 'select[name="appointmentType"], #appointmentType, [data-testid="appointment-type"]',
            'application_type_radio': f'input[value="{self.config.application_type.value}"]',
            'dealer_select': 'select[name="dealer"], #dealerId',
        }

        try:
            # Select dealer/location
            dealer_selector = theoretical_selectors['dealer_select']
            if await self.page.locator(dealer_selector).count() > 0:
                await self.page.select_option(dealer_selector, str(self.config.dealer_id))
                logger.info(f"Selected dealer: {self.config.dealer_id}")

            # Select appointment type
            apt_selector = theoretical_selectors['appointment_type_dropdown']
            if await self.page.locator(apt_selector).count() > 0:
                await self.page.select_option(apt_selector, str(self.config.appointment_type.value))
                logger.info(f"Selected appointment type: {self.config.appointment_type.name}")

            await asyncio.sleep(1)  # Wait for any dynamic updates

        except Exception as e:
            logger.error(f"Error selecting appointment type: {e}")

    async def select_date_and_time(self, date: str, time_slot: str):
        """
        Select a specific date and time slot

        This would interact with a calendar widget or date picker.
        """
        logger.info(f"Selecting date: {date}, time: {time_slot}")

        # Theoretical selectors for date picker
        try:
            # Click on date input to open calendar
            date_input = self.page.locator('input[type="date"], .date-picker, #appointmentDate')
            if await date_input.count() > 0:
                await date_input.click()
                await asyncio.sleep(0.5)

                # Navigate calendar to correct month/day
                # This is highly dependent on the actual calendar widget used

                # For a simple date input:
                await date_input.fill(date.replace('/', '-'))

            # Select time slot
            time_selector = f'[data-time="{time_slot}"], button:has-text("{time_slot}")'
            time_button = self.page.locator(time_selector)
            if await time_button.count() > 0:
                await time_button.click()
                logger.info(f"Selected time slot: {time_slot}")

        except Exception as e:
            logger.error(f"Error selecting date/time: {e}")

    async def fill_applicant_form(self):
        """
        Fill in the applicant information form

        Selectors are theoretical - would need actual inspection.
        """
        logger.info("Filling applicant form...")

        # Mapping of form fields to applicant data
        # Keys are CSS selectors, values are the data to fill
        form_fields = {
            # Name fields
            'input[name="firstName"], #firstName': self.applicant.first_name,
            'input[name="lastName"], #lastName': self.applicant.last_name,

            # ID/Passport
            'input[name="nationalityNumber"], #tcKimlik': self.applicant.nationality_number,
            'input[name="passportNumber"], #passport': self.applicant.passport_number,

            # Contact
            'input[name="email"], #email': self.applicant.email,
            'input[name="phone"], #phone': self.applicant.phone,

            # Birth date
            'input[name="birthDate"], #birthDate': self.applicant.birth_date,
        }

        for selector, value in form_fields.items():
            try:
                field = self.page.locator(selector).first
                if await field.count() > 0:
                    await field.fill(value)
                    logger.debug(f"Filled field {selector}")
                    await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"Could not fill {selector}: {e}")

        logger.info("Form filling complete")

    async def handle_captcha(self) -> bool:
        """
        Handle CAPTCHA if present

        Options:
        1. Manual solving (pause and wait for user)
        2. Audio CAPTCHA solving
        3. Third-party solving service (2captcha, anticaptcha, etc.)
        """
        # Check for common CAPTCHA elements
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            '.g-recaptcha',
            '.h-captcha',
            '#captcha',
        ]

        for selector in captcha_selectors:
            if await self.page.locator(selector).count() > 0:
                logger.warning("CAPTCHA detected!")

                if not self.config.headless:
                    # Manual mode - wait for user to solve
                    logger.info("Please solve the CAPTCHA manually...")
                    self.send_notification("⚠️ CAPTCHA detected! Please solve it manually.")

                    # Wait for CAPTCHA to be solved (check for success indicator)
                    try:
                        await self.page.wait_for_selector(
                            '.recaptcha-success, [data-captcha-solved="true"]',
                            timeout=120000  # 2 minutes
                        )
                        logger.info("CAPTCHA solved!")
                        return True
                    except:
                        logger.error("CAPTCHA solving timeout")
                        return False
                else:
                    # Headless mode - would need automated solving
                    logger.error("CAPTCHA in headless mode - cannot solve automatically")
                    return False

        return True  # No CAPTCHA found

    async def submit_booking(self) -> bool:
        """
        Submit the booking form

        Returns True if successful, False otherwise.
        """
        logger.info("Submitting booking...")

        try:
            # Find and click submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Randevu Al")',
                'button:has-text("Book")',
                'button:has-text("Onayla")',
                '.submit-button',
                '#submitButton',
            ]

            for selector in submit_selectors:
                button = self.page.locator(selector).first
                if await button.count() > 0:
                    await button.click()
                    logger.info("Submit button clicked")
                    break

            # Wait for response
            await asyncio.sleep(2)

            # Check for success indicators
            success_indicators = [
                '.success-message',
                '.confirmation',
                ':has-text("başarılı")',
                ':has-text("successful")',
                ':has-text("confirmation")',
            ]

            for indicator in success_indicators:
                if await self.page.locator(indicator).count() > 0:
                    logger.info("Booking appears successful!")

                    # Take confirmation screenshot
                    await self.page.screenshot(path='screenshots/confirmation.png')

                    return True

            # Check for error indicators
            error_indicators = [
                '.error-message',
                '.alert-danger',
                ':has-text("hata")',
                ':has-text("error")',
            ]

            for indicator in error_indicators:
                element = self.page.locator(indicator).first
                if await element.count() > 0:
                    error_text = await element.text_content()
                    logger.error(f"Booking error: {error_text}")
                    return False

            logger.warning("Could not determine booking result")
            return False

        except Exception as e:
            logger.error(f"Error submitting booking: {e}")
            return False

    async def attempt_booking(self, slot: dict) -> bool:
        """
        Full booking flow for a single slot
        """
        date = slot.get('date', '')
        time_slot = slot.get('hour', slot.get('time', ''))

        logger.info(f"Attempting to book: {date} at {time_slot}")

        try:
            # Navigate to booking page
            await self.navigate_to_booking()

            # Select appointment options
            await self.select_appointment_type()

            # Select date and time
            await self.select_date_and_time(date, time_slot)

            # Fill applicant information
            await self.fill_applicant_form()

            # Handle CAPTCHA if present
            if not await self.handle_captcha():
                return False

            # Submit the form
            success = await self.submit_booking()

            if success:
                self.send_notification(
                    f"✅ BOOKING SUCCESSFUL!\n"
                    f"Date: {date}\n"
                    f"Time: {time_slot}\n"
                    f"Check your email for confirmation."
                )

            return success

        except Exception as e:
            logger.error(f"Booking attempt failed: {e}")
            await self.page.screenshot(path=f'screenshots/error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
            return False

    def send_notification(self, message: str):
        """Send Telegram notification"""
        if not self.config.telegram_token or not self.config.telegram_chat_id:
            logger.info(f"Notification: {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_token}/sendMessage"
            requests.post(url, json={
                "chat_id": self.config.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            })
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")

    async def run(self, auto_book: bool = False):
        """
        Main bot loop

        Args:
            auto_book: If True, automatically attempt booking when slots found
        """
        logger.info("=" * 60)
        logger.info("Kosmos Visa Browser Bot Started")
        logger.info(f"Auto-book: {auto_book}")
        logger.info("=" * 60)

        # Create screenshots directory
        os.makedirs('screenshots', exist_ok=True)

        # Setup browser if auto-booking is enabled
        if auto_book:
            await self.setup_browser()

        try:
            while True:
                logger.info("Scanning for available slots...")

                slots = await self.scan_for_slots()

                if slots:
                    logger.info(f"Found {len(slots)} available slots!")

                    for slot in slots:
                        slot_key = f"{slot.get('date')}_{slot.get('hour', slot.get('time', ''))}"

                        if slot_key in self.notified_slots:
                            continue

                        self.notified_slots.add(slot_key)

                        # Send notification
                        self.send_notification(
                            f"🎫 Slot Available!\n"
                            f"Date: {slot.get('date')}\n"
                            f"Time: {slot.get('hour', slot.get('time', 'N/A'))}\n"
                            f"Quota: {slot.get('quota', 'N/A')}\n"
                            f"Book: {self.BOOKING_URL}"
                        )

                        # Attempt auto-booking if enabled
                        if auto_book:
                            success = await self.attempt_booking(slot)
                            if success:
                                logger.info("Booking successful! Stopping bot.")
                                return

                else:
                    logger.info("No slots available")

                logger.info(f"Next check in {self.config.check_interval} seconds...")
                await asyncio.sleep(self.config.check_interval)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            if auto_book:
                await self.close_browser()


async def main():
    """Example usage"""

    # Applicant information
    applicant = ApplicantInfo(
        first_name="John",
        last_name="Doe",
        nationality_number="12345678901",
        passport_number="U12345678",
        birth_date="1990-01-15",
        email="john.doe@example.com",
        phone="+905551234567"
    )

    # Bot configuration
    config = BookingConfig(
        dealer_id=1,
        application_type=ApplicationType.INDIVIDUAL,
        appointment_type=AppointmentTypeId.STANDARD,
        check_interval=60,
        days_to_check=30,
        headless=False,  # Set True for background
        telegram_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID')
    )

    # Create and run bot
    bot = KosmosBrowserBot(applicant, config)

    await bot.run(
        auto_book=False  # Set True to enable auto-booking (THEORETICAL)
    )


if __name__ == "__main__":
    asyncio.run(main())
