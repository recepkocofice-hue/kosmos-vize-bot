# Kosmos Visa Appointment Bot

A Python bot for monitoring and (theoretically) booking Greek visa appointments from the Kosmos Visa system.

> **⚠️ EDUCATIONAL PURPOSE ONLY**: This project demonstrates web automation concepts. Using automated booking against real systems may violate Terms of Service.

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Availability Monitoring** | Scans next 30 days for open appointment slots |
| 📱 **Telegram Notifications** | Instant alerts when slots become available |
| 🤖 **Browser Automation** | Playwright-based booking (theoretical) |
| ⚙️ **Configurable** | Environment-based configuration |
| 🔄 **Auto-retry** | Continuous monitoring with configurable intervals |

## Project Structure

```
kosmos-vize-bot/
├── bot.py              # Original notification-only bot
├── reservation_bot.py  # API-based reservation bot (theoretical)
├── browser_bot.py      # Browser automation bot (theoretical)
├── config.py           # Configuration management
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
└── readme.md           # This file
```

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/kosmos-vize-bot.git
cd kosmos-vize-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for browser automation)
playwright install chromium
```

### 2. Configuration

Copy the example environment file and edit with your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Telegram (get from @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# Your Information
APPLICANT_FIRST_NAME=John
APPLICANT_LAST_NAME=Doe
APPLICANT_NATIONALITY_NUMBER=12345678901
APPLICANT_PASSPORT_NUMBER=U12345678
APPLICANT_BIRTH_DATE=1990-01-15
APPLICANT_EMAIL=john@example.com
APPLICANT_PHONE=+905551234567

# Bot Settings
DEALER_ID=1
APPLICATION_TYPE=1          # 1=Individual, 2=Family
APPOINTMENT_TYPE=16         # 16=Standard, 18=VIP, 2339=EEA
CHECK_INTERVAL=60           # Seconds between checks
DAYS_TO_CHECK=30
AUTO_BOOK=false
```

### 3. Run the Bot

**Notification Only (Safe):**
```bash
python bot.py
```

**With Theoretical Auto-Booking:**
```bash
python reservation_bot.py
# or
python browser_bot.py
```

## Bot Versions

### 1. `bot.py` - Original Notification Bot

Simple and safe - only monitors and notifies.

```python
# Just checks availability and sends Telegram messages
python bot.py
```

### 2. `reservation_bot.py` - API-Based Bot

Attempts direct API calls for booking (endpoints are theoretical).

```python
from reservation_bot import KosmosReservationBot, ApplicantInfo, DealerId

applicant = ApplicantInfo(
    first_name="John",
    last_name="Doe",
    nationality_number="12345678901",
    passport_number="U12345678",
    birth_date="1990-01-15",
    email="john@example.com",
    phone="+905551234567"
)

bot = KosmosReservationBot(
    applicant=applicant,
    dealer_id=DealerId.ISTANBUL,
    application_type=ApplicationType.INDIVIDUAL,
    appointment_type=AppointmentTypeId.STANDARD
)

bot.run(auto_book=False)  # Set True for auto-booking
```

### 3. `browser_bot.py` - Browser Automation Bot

Uses Playwright to control a real browser - most realistic approach.

```python
import asyncio
from browser_bot import KosmosBrowserBot, ApplicantInfo, BookingConfig

applicant = ApplicantInfo(...)
config = BookingConfig(
    headless=False,  # Show browser window
    check_interval=60
)

bot = KosmosBrowserBot(applicant, config)
asyncio.run(bot.run(auto_book=True))
```

## Configuration Reference

### Application Types

| Value | Name | Description |
|-------|------|-------------|
| 1 | INDIVIDUAL | Single applicant |
| 2 | FAMILY | Family application |

### Appointment Types

| Value | Name | Description |
|-------|------|-------------|
| 16 | STANDARD | Standard visa appointment |
| 18 | VIP | VIP service |
| 2339 | EEA_AB_SPOUSE | EEA/AB Spouse |

### Dealer IDs

| Value | Location |
|-------|----------|
| 1 | Istanbul |
| 2 | Ankara (theoretical) |
| 3 | Izmir (theoretical) |

## API Reference

### Known Endpoints

```
GET https://api.kosmosvize.com.tr/api/AppointmentLayouts/GetAppointmentHourQoutaInfo
    ?nationalityNumber=<TC_NO>
    &dealerId=<DEALER_ID>
    &date=<YYYY/MM/DD>
    &appointmentTypeId=<TYPE_ID>
    &onlyAvailable=true
    &applicationType=<APP_TYPE>
```

### Theoretical Booking Endpoints

These would need to be discovered via network analysis:

```
POST /api/Appointments/Create
POST /api/Booking/Submit
POST /api/Reservation/Create
```

## Telegram Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token
4. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)
5. Add both to your `.env` file

## Technical Notes

### Why curl_cffi?

The Kosmos API has anti-bot protection. `curl_cffi` impersonates real browser TLS fingerprints:

```python
response = requests.get(url, impersonate="chrome")
```

### Browser Automation Stealth

The browser bot includes anti-detection measures:

- Removes `navigator.webdriver` flag
- Sets realistic viewport and user agent
- Uses human-like delays
- Handles CAPTCHAs (manual mode)

### Rate Limiting

The bot includes delays between requests to avoid being blocked:
- 0.3-0.5s between API calls
- Configurable main loop interval

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 Forbidden | Anti-bot protection triggered. Wait and retry. |
| No slots found | Normal - slots are rare. Keep bot running. |
| Telegram not sending | Check bot token and chat ID. |
| Browser crashes | Run with `headless=False` to debug. |

## Disclaimer

This project is for **educational purposes only**. It demonstrates:
- Web scraping and API interaction
- Browser automation with Playwright
- Telegram bot integration
- Configuration management

**Using automated tools against real booking systems may:**
- Violate Terms of Service
- Result in IP/account bans
- Be unfair to other applicants

Always check and comply with the target website's Terms of Service.

## License

MIT License - See LICENSE file for details.
