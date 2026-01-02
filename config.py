"""
Configuration management for Kosmos Visa Bot

Loads settings from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class ApplicationType(Enum):
    INDIVIDUAL = 1
    FAMILY = 2

    @classmethod
    def from_value(cls, value: int) -> 'ApplicationType':
        for member in cls:
            if member.value == value:
                return member
        return cls.INDIVIDUAL


class AppointmentTypeId(Enum):
    STANDARD = 16
    VIP = 18
    EEA_AB_SPOUSE = 2339

    @classmethod
    def from_value(cls, value: int) -> 'AppointmentTypeId':
        for member in cls:
            if member.value == value:
                return member
        return cls.STANDARD


class DealerId(Enum):
    """Known dealer/location IDs"""
    ISTANBUL = 1
    # Add more as discovered


@dataclass
class ApplicantConfig:
    """Applicant information loaded from environment"""
    first_name: str = field(default_factory=lambda: os.getenv('APPLICANT_FIRST_NAME', ''))
    last_name: str = field(default_factory=lambda: os.getenv('APPLICANT_LAST_NAME', ''))
    nationality_number: str = field(default_factory=lambda: os.getenv('APPLICANT_NATIONALITY_NUMBER', ''))
    passport_number: str = field(default_factory=lambda: os.getenv('APPLICANT_PASSPORT_NUMBER', ''))
    birth_date: str = field(default_factory=lambda: os.getenv('APPLICANT_BIRTH_DATE', ''))
    email: str = field(default_factory=lambda: os.getenv('APPLICANT_EMAIL', ''))
    phone: str = field(default_factory=lambda: os.getenv('APPLICANT_PHONE', ''))

    def is_valid(self) -> bool:
        """Check if all required fields are filled"""
        required = [
            self.first_name,
            self.last_name,
            self.nationality_number,
            self.email,
            self.phone
        ]
        return all(required)


@dataclass
class TelegramConfig:
    """Telegram notification settings"""
    bot_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    chat_id: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass
class BotConfig:
    """Main bot configuration"""
    # Appointment settings
    dealer_id: int = field(default_factory=lambda: int(os.getenv('DEALER_ID', '1')))
    application_type: ApplicationType = field(
        default_factory=lambda: ApplicationType.from_value(int(os.getenv('APPLICATION_TYPE', '1')))
    )
    appointment_type: AppointmentTypeId = field(
        default_factory=lambda: AppointmentTypeId.from_value(int(os.getenv('APPOINTMENT_TYPE', '16')))
    )

    # Timing
    check_interval: int = field(default_factory=lambda: int(os.getenv('CHECK_INTERVAL', '60')))
    days_to_check: int = field(default_factory=lambda: int(os.getenv('DAYS_TO_CHECK', '30')))

    # Auto-booking
    auto_book: bool = field(default_factory=lambda: os.getenv('AUTO_BOOK', 'false').lower() == 'true')

    # Browser settings
    headless: bool = field(default_factory=lambda: os.getenv('HEADLESS', 'false').lower() == 'true')

    # Preferred dates/times (comma-separated)
    preferred_dates: List[str] = field(default_factory=lambda: _parse_list(os.getenv('PREFERRED_DATES', '')))
    preferred_times: List[str] = field(default_factory=lambda: _parse_list(os.getenv('PREFERRED_TIMES', '')))


def _parse_list(value: str) -> List[str]:
    """Parse comma-separated string to list"""
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def load_config():
    """Load all configuration"""
    return {
        'applicant': ApplicantConfig(),
        'telegram': TelegramConfig(),
        'bot': BotConfig()
    }


def validate_config() -> List[str]:
    """Validate configuration and return list of errors"""
    errors = []
    config = load_config()

    if not config['applicant'].is_valid():
        errors.append("Applicant information incomplete. Check APPLICANT_* environment variables.")

    if not config['telegram'].is_configured():
        errors.append("Telegram not configured. Notifications will be logged only.")

    return errors


if __name__ == "__main__":
    # Test configuration loading
    print("Loading configuration...")
    config = load_config()

    print("\nApplicant Config:")
    print(f"  Name: {config['applicant'].first_name} {config['applicant'].last_name}")
    print(f"  Valid: {config['applicant'].is_valid()}")

    print("\nTelegram Config:")
    print(f"  Configured: {config['telegram'].is_configured()}")

    print("\nBot Config:")
    print(f"  Dealer ID: {config['bot'].dealer_id}")
    print(f"  Application Type: {config['bot'].application_type.name}")
    print(f"  Appointment Type: {config['bot'].appointment_type.name}")
    print(f"  Check Interval: {config['bot'].check_interval}s")
    print(f"  Auto-book: {config['bot'].auto_book}")

    errors = validate_config()
    if errors:
        print("\nConfiguration Errors:")
        for error in errors:
            print(f"  - {error}")
