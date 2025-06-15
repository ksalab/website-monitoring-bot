# Website Monitoring Bot

A Telegram bot that monitors website availability and SSL certificate status, sending notifications to a specified Telegram group when issues are detected.

## Features

- HTTP Status Monitoring: Checks website availability (e.g., `200 OK`, `down`).
- SSL Certificate Monitoring: Tracks SSL validity, expiration dates, and remaining days.
- Domain Expiration Monitoring: Retrieves domain expiration dates via WHOIS and calculates remaining days.
- Per-User Configuration: Stores monitored sites in `data/<user_id>.json` for each Telegram user.
- Formatted Status Reports: Sends detailed `/status` messages with emojis (🟢/🔴) and clickable registrar links.
- Commands:
  - `/start`: Initializes the bot and displays a welcome message.
  - `/status`: Reports the current status of all monitored websites, including HTTP, SSL, and domain details.
  - `/listsites`: Lists all websites currently monitored for the user.
  - `/addsite <url>`: Adds a new website to monitoring (e.g., `/addsite https://example.com`).
  - `/removesite <url>`: Removes a website from monitoring (e.g., `/removesite https://example.com`). Supports interactive mode via `/listsites`.
- Logging: Detailed logs with rotation and compression in `logs/bot.log`.
- Error Handling: Gracefully handles WHOIS errors, showing cached data with last-checked timestamps.

Example `/status` Output

```sh
🌐 https://ksalab.xyz
Status: 🟢 200 OK
--- SSL ---
Valid: True
Expires: 2025-07-16 10:29:32
Days Left: 32
--- Domain ---
Expires: 2027-08-16 23:59:59
Days Left: 794
Registrar: GoDaddy.com, LLC
```

Note: `GoDaddy.com, LLC` is a clickable link to the registrar's website.

## Installation

### Prerequisites

- Python 3.8 or higher
- A Telegram bot token (obtained via @BotFather)
- A Telegram group ID and optional topic ID
- Dependencies listed in `requirements.txt`

### Steps

1. Clone the repository:
  ```sh
  git clone https://github.com/your-username/website-monitoring-bot.git
  cd website-monitoring-bot
  ```

2. Set up a virtual environment (optional but recommended):

  ```sh
  python -m venv .venv
  source .venv/bin/activate  # On Windows: .venv\Scripts\activate
  ```

3. Install dependencies:

  ```sh
  pip install -r requirements.txt
  ```

4. Create a `.env` file in the project root with the following content:

  ```env
  BOT_TOKEN=your_bot_token
  GROUP_ID=your_group_id
  TOPIC_ID=your_topic_id  # Optional
  CHECK_INTERVAL=3600     # Check interval in seconds
  ```

  - `BOT_TOKEN`: Obtain from @BotFather.
  - `GROUP_ID`: The Telegram group ID (e.g., `-1001234567890`).
  - `TOPIC_ID`: The topic ID within the group (optional).
  - `CHECK_INTERVAL`: Time between checks (default: 3600 seconds = 1 hour).

5. Configure monitored sites:

- Add websites using `/addsite <url>` or via the "Add site" button in `/listsites`.
- Example `data/123456789.json`:

  ```json
  [
    {
      "url": "https://ksalab.xyz",
      "ssl_valid": null,
      "ssl_expires": null,
      "domain_expires": null,
      "domain_last_checked": null,
      "domain_notifications": [],
      "ssl_notifications": []
    }
  ]
  ```

6. Run the bot:

  ```sh
  python bot.py
  ```

## Project Structure

```plain
website-monitoring-bot/
├── bot.py              # Main bot entry point
├── modules/           # Core bot modules
│   ├── checks.py      # HTTP, SSL, and WHOIS check functions
│   ├── config.py      # Configuration constants
│   ├── handlers.py    # Telegram command handlers
│   ├── logging.py     # Logging setup
│   ├── notifications.py # Notification logic
│   └── storage.py     # Data storage functions
├── data/              # User-specific site configurations (<user_id>.json)
├── logs/              # Log files (bot.log, rotated with .gz)
├── .env               # Environment variables
├── CHANGELOG.md       # Project changelog
├── README.md          # This file
├── requirements.txt   # Python dependencies
└── VERSION            # Current version (1.3.2)
```

## Dependencies

- `aiogram==3.20.0.post0`: Telegram bot framework
- `python-whois`: WHOIS queries for domain expiration
- `requests`: HTTP status checks
- `pyOpenSSL`: SSL certificate validation
- `python-dotenv`: Environment variable management
- See `requirements.txt` for full list.

## Changelog

See in [CHANGELOG.md](./CHANGELOG.md)

## License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

- Fork the repository.
- Create a feature branch (git checkout -b feature/your-feature).
- Commit changes (git commit -m "Add your feature").
- Push to the branch (git push origin feature/your-feature).
- Open a Pull Request.

## Contact

For questions or support, open an issue on GitHub.
