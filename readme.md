# Kosmos Visa Appointment Bot

A Python bot for monitoring and (theoretically) booking Greek visa appointments from the Kosmos Visa system.

> **⚠️ EDUCATIONAL PURPOSE ONLY**: This project demonstrates web automation concepts. Using automated booking against real systems may violate Terms of Service.

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Fast Monitoring** | Parallel API scanning of 30 days in ~2 seconds |
| 📱 **Telegram Alerts** | Instant notifications with booking links |
| 🤖 **Auto-Booking** | Browser automation for form filling (theoretical) |
| 💾 **State Persistence** | SQLite-based, survives restarts |
| 🔧 **Highly Configurable** | Environment-based with CLI overrides |
| 🐳 **Docker Ready** | Easy deployment with docker-compose |

## Project Structure

```
kosmos-vize-bot/
├── hybrid_bot.py       # ⭐ RECOMMENDED - Hybrid approach
├── bot.py              # Original notification-only bot
├── reservation_bot.py  # API-based reservation bot
├── browser_bot.py      # Browser-only automation bot
├── config.py           # Configuration management
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── Dockerfile          # Docker build file
├── docker-compose.yml  # Docker compose config
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

# Install Playwright browsers (for auto-booking)
playwright install chromium
```

### 2. Configuration

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run

```bash
# Monitor only (recommended to start)
python hybrid_bot.py

# With auto-booking enabled
python hybrid_bot.py --auto-book

# Check every 30 seconds
python hybrid_bot.py -i 30

# Run in background (headless browser)
python hybrid_bot.py --auto-book --headless
```

## Bot Versions Comparison

| Feature | `hybrid_bot.py` | `bot.py` | `browser_bot.py` |
|---------|-----------------|----------|------------------|
| **Recommended** | ⭐ Yes | For simple use | No |
| Parallel scanning | ✅ | ❌ | ✅ |
| State persistence | ✅ SQLite | ❌ | ❌ |
| CLI interface | ✅ | ❌ | ❌ |
| Auto-booking | ✅ | ❌ | ✅ |
| Docker support | ✅ | ❌ | ❌ |
| CAPTCHA handling | ✅ Manual | N/A | ✅ Manual |

## Hybrid Bot Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYBRID BOT FLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   MONITOR   │───▶│   NOTIFY    │───▶│   BOOK (optional)   │ │
│  │  (API Fast) │    │  (Telegram) │    │  (Browser Reliable) │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│        │                   │                      │             │
│        ▼                   ▼                      ▼             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              STATE MANAGER (SQLite)                      │   │
│  │  • Tracks notified slots (no duplicates)                 │   │
│  │  • Logs booking attempts                                 │   │
│  │  • Persists across restarts                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## CLI Options

```bash
python hybrid_bot.py [OPTIONS]

Options:
  -a, --auto-book     Enable automatic booking when slots found
  --headless          Run browser in background (no window)
  -i, --interval N    Check every N seconds (default: 60)
  -d, --days N        Check N days ahead (default: 30)
  -v, --verbose       Enable debug logging
```

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Required |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Required |
| `DEALER_ID` | Location ID | 1 (Istanbul) |
| `APPLICATION_TYPE` | 1=Individual, 2=Family | 1 |
| `APPOINTMENT_TYPE` | 16=Standard, 18=VIP | 16 |
| `CHECK_INTERVAL` | Seconds between checks | 60 |
| `DAYS_TO_CHECK` | Days to scan ahead | 30 |
| `MIN_QUOTA` | Minimum slots to trigger | 1 |
| `AUTO_BOOK` | Enable auto-booking | false |
| `HEADLESS` | Hide browser window | false |
| `PREFERRED_DATES` | Only these dates (comma-sep) | All |
| `PREFERRED_TIMES` | Time ranges (e.g., 09:00-12:00) | All |

### Appointment Types

| Value | Name | Description |
|-------|------|-------------|
| 16 | STANDARD | Standard visa appointment |
| 18 | VIP | VIP service |
| 2339 | EEA_AB_SPOUSE | EEA/AB Spouse |

## API Reference

### Known Working Endpoint

```http
GET https://api.kosmosvize.com.tr/api/AppointmentLayouts/GetAppointmentHourQoutaInfo
    ?nationalityNumber=<TC_NO>
    &dealerId=<DEALER_ID>
    &date=<YYYY/MM/DD>
    &appointmentTypeId=<TYPE_ID>
    &onlyAvailable=true
    &applicationType=<APP_TYPE>
```

## Telegram Setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the bot token
3. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID
4. Add both to `.env`

## Technical Details

### Why curl_cffi?

Bypasses TLS fingerprinting with browser impersonation:
```python
response = requests.get(url, impersonate="chrome")
```

### Stealth Measures

- Removes `navigator.webdriver` detection
- Realistic viewport, user agent, locale
- Human-like delays between actions
- Proper browser fingerprinting

### State Persistence

SQLite database (`bot_state.db`) stores:
- Notified slots (avoids duplicate alerts)
- Booking attempts (for debugging)
- Successful bookings (auto-stops after success)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 Forbidden | Wait 5 minutes, anti-bot triggered |
| No slots found | Normal - keep running |
| Telegram fails | Verify token and chat ID |
| Browser crashes | Use `--verbose` to debug |
| CAPTCHA timeout | Increase `BOOKING_TIMEOUT` |

## Disclaimer

**EDUCATIONAL PURPOSE ONLY**

This project demonstrates:
- Async Python and parallel processing
- Web API interaction with anti-bot bypass
- Browser automation with Playwright
- Telegram bot integration
- State management with SQLite
- Docker containerization

Using automated tools against real booking systems may violate Terms of Service and result in bans.

## License

MIT License
