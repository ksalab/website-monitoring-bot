# Website Monitoring Bot

A Telegram bot that monitors website availability and SSL certificate status, sending notifications to a specified Telegram group when issues are detected.

## Features

- Monitors website HTTP status codes (e.g., 200 OK, 404 Not Found).
- Checks SSL certificate validity and expiration dates.
- Sends alerts to a Telegram group (with optional topic) when a website is down or has SSL issues.
- Supports periodic checks with configurable intervals.
- Provides a `/status` command to view current website statuses.
- Logs monitoring activity to a file (`bot.log`) and console.

## Installation

### Prerequisites

- Python 3.8 or higher
- `git` installed
- A Telegram bot token (obtained via @BotFather)
- A Telegram group ID and optional topic ID

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

5. Configure sites.json:

Create or edit `sites.json` to list the websites to monitor:

  ```json
  [
      {"url": "https://example.com"},
      {"url": "https://another-site.org"}
  ]
  ```

6. Run the bot:

  ```sh
  python bot.py
  ```

## Configuration

- Bot Commands:

  - `/start`: Initializes the bot and displays a welcome message.
  - `/status`: Returns the current status of all monitored websites, including HTTP status and SSL certificate details.

- Notifications:

  - The bot sends alerts to the configured Telegram group when:
    - A website returns a non-200 HTTP status.
    - An SSL certificate is invalid or expired.

- Logging:

  - Logs are written to bot.log and displayed in the console.
  - Logs include website check results, command executions, and errors.

## Example Usage

1. Add the bot to your Telegram group and make it an admin.
2. Send `/start` to verify the bot is running.
3. Use `/status` to check website statuses.
4. The bot will automatically notify the group if issues are detected.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## Contact

For questions or support, open an issue on GitHub.
