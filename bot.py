import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.exceptions import TelegramConflictError
from modules.config import load_config
from modules.logging import setup_logging
from modules.handlers import router, BOT_COMMANDS_CONFIG
from modules.notifications import monitor_websites

logger = logging.getLogger(__name__)


async def main():
    """Initialize and run the Telegram bot."""
    try:
        setup_logging()
        config = load_config()
        bot = Bot(token=config["BOT_TOKEN"])
        dp = Dispatcher()

        # Set bot commands
        await bot.set_my_commands(
            [
                BotCommand(command=command, description=description)
                for command, description in BOT_COMMANDS_CONFIG.items()
            ]
        )
        logger.info("Bot commands set successfully")

        dp.include_router(router)

        # Clear existing webhook
        await bot.delete_webhook()
        logger.info("Webhook cleared successfully")

        # Start monitoring task
        asyncio.create_task(
            monitor_websites(bot, config, config["CHECK_INTERVAL"])
        )
        logger.info("Monitoring task started")

        # Start polling
        logger.info("Starting bot polling")
        await dp.start_polling(bot)
    except TelegramConflictError as e:
        logger.error(
            f"Bot failed to start due to conflict: {e}. Ensure only one bot instance is running."
        )
        raise
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
