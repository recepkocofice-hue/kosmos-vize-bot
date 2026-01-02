"""
Kosmos Visa Appointment Reservation Bot (Theoretical/Educational)

This is a THEORETICAL implementation for educational purposes.
It demonstrates how an automated booking system might work.

WARNING: Using this against real systems may violate Terms of Service.
"""

import time
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from curl_cffi import requests
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reservation_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ApplicationType(Enum):
    INDIVIDUAL = 1  # Bireysel
    FAMILY = 2      # Aile


class AppointmentTypeId(Enum):
    STANDARD = 16       # Standart
    VIP = 18            # Vip
    EEA_AB_SPOUSE = 2339  # EEA AB Eşi


class DealerId(Enum):
    """Dealer/Location IDs - These are theoretical values"""
    ISTANBUL = 1
    ANKARA = 2
    IZMIR = 3


@dataclass
class ApplicantInfo:
    """Applicant information required for booking"""
    first_name: str
    last_name: str
    nationality_number: str  # TC Kimlik No or Passport
    passport_number: str
    birth_date: str  # YYYY-MM-DD
    email: str
    phone: str
    # For family applications
    family_members: Optional[List[Dict[str, str]]] = None


@dataclass
class AppointmentSlot:
    """Represents an available appointment slot"""
    date: str
    time: str
    slot_id: str
    quota: int


class KosmosReservationBot:
    """
    Theoretical Kosmos Visa Reservation Bot

    This class demonstrates the architecture of an automated booking system.
    """

    BASE_URL = "https://api.kosmosvize.com.tr/api"
    BOOKING_PORTAL = "https://basvuru.kosmosvize.com.tr"

    # Common headers to mimic browser
    DEFAULT_HEADERS = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9,tr;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://basvuru.kosmosvize.com.tr',
        'referer': 'https://basvuru.kosmosvize.com.tr/',
        'sec-ch-ua': '"Google Chrome";v="131", "Not=A?Brand";v="8", "Chromium";v="131"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }

    def __init__(
        self,
        applicant: ApplicantInfo,
        dealer_id: DealerId,
        application_type: ApplicationType,
        appointment_type: AppointmentTypeId,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None
    ):
        self.applicant = applicant
        self.dealer_id = dealer_id
        self.application_type = application_type
        self.appointment_type = appointment_type
        self.telegram_token = telegram_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID')

        # Session for maintaining cookies
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

        # Track already notified slots to avoid duplicates
        self.notified_slots: set = set()

        # Booking state
        self.auth_token: Optional[str] = None
        self.session_id: Optional[str] = None

    def get_available_slots(self, date: str, only_available: bool = True) -> List[AppointmentSlot]:
        """
        Fetch available appointment slots for a given date.
        This uses the known working endpoint.
        """
        url = f"{self.BASE_URL}/AppointmentLayouts/GetAppointmentHourQoutaInfo"

        params = {
            'nationalityNumber': self.applicant.nationality_number,
            'dealerId': self.dealer_id.value,
            'date': date,
            'appointmentTypeId': self.appointment_type.value,
            'onlyAvailable': str(only_available).lower(),
            'applicationType': self.application_type.value
        }

        try:
            response = self.session.get(url, params=params, impersonate="chrome")
            response.raise_for_status()
            data = response.json()

            slots = []
            if isinstance(data, list):
                for item in data:
                    # Parse the response - structure is theoretical
                    slot = AppointmentSlot(
                        date=date,
                        time=item.get('hour', item.get('time', '')),
                        slot_id=str(item.get('id', item.get('slotId', ''))),
                        quota=item.get('quota', item.get('availableCount', 0))
                    )
                    if slot.quota > 0:
                        slots.append(slot)

            return slots

        except Exception as e:
            logger.error(f"Error fetching slots for {date}: {e}")
            return []

    def scan_date_range(self, days: int = 30) -> List[AppointmentSlot]:
        """Scan multiple days for available slots"""
        all_slots = []

        for i in range(days):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y/%m/%d")
            slots = self.get_available_slots(date)
            all_slots.extend(slots)

            if slots:
                logger.info(f"Found {len(slots)} slots on {date}")

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        return all_slots

    def _init_booking_session(self) -> bool:
        """
        Initialize a booking session (THEORETICAL)

        In reality, this would:
        1. Load the booking portal page
        2. Extract CSRF tokens
        3. Initialize session cookies
        4. Possibly solve a CAPTCHA
        """
        logger.info("Initializing booking session...")

        # Theoretical: Get initial page to establish session
        try:
            # This endpoint is theoretical
            response = self.session.get(
                f"{self.BOOKING_PORTAL}/",
                impersonate="chrome"
            )

            # Extract session cookies
            self.session_id = self.session.cookies.get('session_id')

            # In reality, you'd parse the HTML for CSRF tokens
            # self.csrf_token = extract_csrf_from_html(response.text)

            logger.info("Booking session initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize session: {e}")
            return False

    def _prepare_booking_payload(self, slot: AppointmentSlot) -> Dict[str, Any]:
        """
        Prepare the booking request payload (THEORETICAL)

        This is based on common patterns in visa booking systems.
        Actual field names would need to be discovered via network analysis.
        """
        payload = {
            # Appointment selection
            "appointmentDate": slot.date,
            "appointmentTime": slot.time,
            "slotId": slot.slot_id,
            "dealerId": self.dealer_id.value,
            "appointmentTypeId": self.appointment_type.value,
            "applicationType": self.application_type.value,

            # Primary applicant info
            "applicant": {
                "firstName": self.applicant.first_name,
                "lastName": self.applicant.last_name,
                "nationalityNumber": self.applicant.nationality_number,
                "passportNumber": self.applicant.passport_number,
                "birthDate": self.applicant.birth_date,
                "email": self.applicant.email,
                "phone": self.applicant.phone
            },

            # For family applications
            "familyMembers": self.applicant.family_members or [],

            # Session/security tokens (theoretical)
            # "csrfToken": self.csrf_token,
            # "captchaResponse": captcha_solution,
        }

        return payload

    def reserve_slot(self, slot: AppointmentSlot) -> bool:
        """
        Attempt to reserve an appointment slot (THEORETICAL)

        This demonstrates the booking flow:
        1. Initialize session
        2. Prepare booking data
        3. Submit reservation
        4. Handle response
        """
        logger.info(f"Attempting to reserve slot: {slot.date} {slot.time}")

        # Step 1: Initialize session
        if not self._init_booking_session():
            return False

        # Step 2: Prepare payload
        payload = self._prepare_booking_payload(slot)

        # Step 3: Submit reservation (THEORETICAL ENDPOINT)
        # The actual endpoint would need to be discovered via network analysis
        theoretical_endpoints = [
            f"{self.BASE_URL}/Appointments/Create",
            f"{self.BASE_URL}/Booking/Submit",
            f"{self.BASE_URL}/Reservation/Create",
            f"{self.BASE_URL}/AppointmentLayouts/BookAppointment",
        ]

        # In reality, you'd know the correct endpoint
        booking_url = theoretical_endpoints[0]

        try:
            logger.info(f"Submitting reservation to {booking_url}")

            response = self.session.post(
                booking_url,
                json=payload,
                impersonate="chrome"
            )

            # Handle response
            if response.status_code == 200:
                result = response.json()

                # Check for success (field names are theoretical)
                if result.get('success') or result.get('isSuccess') or result.get('status') == 'confirmed':
                    confirmation_id = result.get('confirmationId', result.get('bookingId', 'N/A'))
                    logger.info(f"✅ Reservation successful! Confirmation: {confirmation_id}")
                    self.send_notification(
                        f"✅ APPOINTMENT BOOKED!\n"
                        f"Date: {slot.date}\n"
                        f"Time: {slot.time}\n"
                        f"Confirmation: {confirmation_id}"
                    )
                    return True
                else:
                    error_msg = result.get('message', result.get('error', 'Unknown error'))
                    logger.warning(f"Booking failed: {error_msg}")
                    return False

            elif response.status_code == 409:
                logger.warning("Slot already taken (conflict)")
                return False

            elif response.status_code == 429:
                logger.warning("Rate limited - waiting before retry")
                time.sleep(30)
                return False

            else:
                logger.error(f"Booking failed with status {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error during reservation: {e}")
            return False

    def send_notification(self, message: str):
        """Send notification via Telegram"""
        if not self.telegram_token or not self.telegram_chat_id:
            logger.info(f"Notification (no Telegram configured): {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            requests.post(url, json=data)
            logger.info("Telegram notification sent")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def run(
        self,
        check_interval: int = 60,
        days_to_check: int = 30,
        auto_book: bool = False,
        preferred_dates: Optional[List[str]] = None,
        preferred_times: Optional[List[str]] = None
    ):
        """
        Main bot loop

        Args:
            check_interval: Seconds between checks
            days_to_check: Number of days to scan
            auto_book: If True, automatically attempt to book (THEORETICAL)
            preferred_dates: List of preferred dates (YYYY/MM/DD format)
            preferred_times: List of preferred time ranges (e.g., ["09:00-12:00"])
        """
        logger.info("=" * 50)
        logger.info("Kosmos Visa Reservation Bot Started")
        logger.info(f"Dealer: {self.dealer_id.name}")
        logger.info(f"Type: {self.appointment_type.name}")
        logger.info(f"Auto-book: {auto_book}")
        logger.info("=" * 50)

        self.send_notification(
            f"🤖 Bot Started\n"
            f"Checking every {check_interval}s for {days_to_check} days"
        )

        while True:
            try:
                logger.info("Scanning for available slots...")
                slots = self.scan_date_range(days_to_check)

                if slots:
                    # Filter by preferences if specified
                    filtered_slots = self._filter_slots(slots, preferred_dates, preferred_times)

                    for slot in filtered_slots:
                        slot_key = f"{slot.date}_{slot.time}"

                        # Skip already notified slots
                        if slot_key in self.notified_slots:
                            continue

                        self.notified_slots.add(slot_key)

                        message = (
                            f"🎫 Slot Available!\n"
                            f"Date: {slot.date}\n"
                            f"Time: {slot.time}\n"
                            f"Quota: {slot.quota}\n"
                            f"Book now: {self.BOOKING_PORTAL}"
                        )

                        logger.info(message)
                        self.send_notification(message)

                        # Auto-book if enabled (THEORETICAL)
                        if auto_book:
                            logger.info("Auto-booking enabled - attempting reservation...")
                            success = self.reserve_slot(slot)
                            if success:
                                logger.info("Booking successful! Stopping bot.")
                                return
                else:
                    logger.info("No available slots found")

                # Clear old notified slots (older than 1 hour)
                # In a real implementation, you'd track timestamps

                logger.info(f"Waiting {check_interval} seconds before next check...")
                time.sleep(check_interval)

            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)  # Brief pause before retry

    def _filter_slots(
        self,
        slots: List[AppointmentSlot],
        preferred_dates: Optional[List[str]],
        preferred_times: Optional[List[str]]
    ) -> List[AppointmentSlot]:
        """Filter slots by user preferences"""
        filtered = slots

        if preferred_dates:
            filtered = [s for s in filtered if s.date in preferred_dates]

        if preferred_times:
            # Simple time range filtering
            # Format: ["09:00-12:00", "14:00-17:00"]
            def time_in_range(slot_time: str, ranges: List[str]) -> bool:
                for time_range in ranges:
                    if '-' in time_range:
                        start, end = time_range.split('-')
                        if start <= slot_time <= end:
                            return True
                return False

            filtered = [s for s in filtered if time_in_range(s.time, preferred_times)]

        return filtered


def main():
    """Example usage"""

    # Configure applicant information
    applicant = ApplicantInfo(
        first_name="John",
        last_name="Doe",
        nationality_number="12345678901",  # TC Kimlik No
        passport_number="U12345678",
        birth_date="1990-01-15",
        email="john.doe@example.com",
        phone="+905551234567"
    )

    # Create bot instance
    bot = KosmosReservationBot(
        applicant=applicant,
        dealer_id=DealerId.ISTANBUL,
        application_type=ApplicationType.INDIVIDUAL,
        appointment_type=AppointmentTypeId.STANDARD,
        telegram_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID')
    )

    # Run the bot
    bot.run(
        check_interval=60,          # Check every minute
        days_to_check=30,           # Scan next 30 days
        auto_book=False,            # Set to True to enable auto-booking (THEORETICAL)
        preferred_dates=None,       # Or specify: ["2026/01/15", "2026/01/16"]
        preferred_times=None        # Or specify: ["09:00-12:00"]
    )


if __name__ == "__main__":
    main()
