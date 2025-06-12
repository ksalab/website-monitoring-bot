import asyncio
import json
import logging
import os
import ssl
import socket
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TypedDict
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message, BotCommand
from aiogram.exceptions import TelegramBadRequest, TelegramConflictError
from dotenv import load_dotenv
import certifi
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import urlparse
import whois

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("bot.log", mode="a"),
        logging.StreamHandler(),
    ],
)

# Initialize router
router = Router()


# Type definitions
class SiteConfig(TypedDict):
    url: str
    ssl_valid: Optional[bool]
    ssl_expires: Optional[str]
    domain_expires: Optional[str]
    domain_last_checked: Optional[str]
    domain_notifications: List[int]
    ssl_notifications: List[int]


class WebsiteStatus(TypedDict):
    url: str
    status: str
    error: Optional[str]


class SSLStatus(TypedDict):
    url: str
    ssl_status: str
    expires: Optional[str]
    error: Optional[str]


class DomainStatus(TypedDict):
    url: str
    expires: Optional[str]
    error: Optional[str]


def load_config() -> Dict[str, any]:
    """Load configuration from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    logger.info(f"Loading .env from: {env_path}")
    load_dotenv(env_path, override=True)

    logger.debug(
        f"Environment variables: BOT_TOKEN={os.environ.get('BOT_TOKEN', 'Not set')}, "
        f"GROUP_ID={os.environ.get('GROUP_ID', 'Not set')}, "
        f"USER_ID={os.environ.get('USER_ID', 'Not set')}"
    )

    config = {
        "BOT_TOKEN": os.getenv("BOT_TOKEN"),
        "GROUP_ID": os.getenv("GROUP_ID"),
        "TOPIC_ID": os.getenv("TOPIC_ID"),
        "CHECK_INTERVAL": os.getenv("CHECK_INTERVAL", "3600")
        .split("#")[0]
        .strip(),
        "DOMAIN_EXPIRY_THRESHOLD": os.getenv(
            "DOMAIN_EXPIRY_THRESHOLD", "30,15,7,1"
        )
        .split("#")[0]
        .strip(),
        "SSL_EXPIRY_THRESHOLD": os.getenv("SSL_EXPIRY_THRESHOLD", "30,15,7,1")
        .split("#")[0]
        .strip(),
        "NOTIFICATION_MODE": os.getenv("NOTIFICATION_MODE", "group")
        .split("#")[0]
        .strip(),
        "USER_ID": os.getenv("USER_ID"),
    }

    if not config["BOT_TOKEN"]:
        raise ValueError("BOT_TOKEN is required")

    if config["NOTIFICATION_MODE"] not in ["group", "user"]:
        raise ValueError(
            f"NOTIFICATION_MODE must be 'group' or 'user', got: {config['NOTIFICATION_MODE']!r}"
        )

    if config["NOTIFICATION_MODE"] == "group" and not config["GROUP_ID"]:
        raise ValueError(
            "GROUP_ID is required when NOTIFICATION_MODE is 'group'"
        )

    if config["NOTIFICATION_MODE"] == "user" and not config["USER_ID"]:
        raise ValueError(
            "USER_ID is required when NOTIFICATION_MODE is 'user'"
        )

    try:
        config["CHECK_INTERVAL"] = int(config["CHECK_INTERVAL"])
    except ValueError:
        raise ValueError(
            f"CHECK_INTERVAL must be a valid integer, got: {config['CHECK_INTERVAL']!r}"
        )

    try:
        config["DOMAIN_EXPIRY_THRESHOLD"] = [
            int(x) for x in config["DOMAIN_EXPIRY_THRESHOLD"].split(",")
        ]
    except ValueError:
        raise ValueError(
            f"DOMAIN_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['DOMAIN_EXPIRY_THRESHOLD']!r}"
        )

    try:
        config["SSL_EXPIRY_THRESHOLD"] = [
            int(x) for x in config["SSL_EXPIRY_THRESHOLD"].split(",")
        ]
    except ValueError:
        raise ValueError(
            f"SSL_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['SSL_EXPIRY_THRESHOLD']!r}"
        )

    if config["TOPIC_ID"]:
        try:
            config["TOPIC_ID"] = config["TOPIC_ID"].split("#")[0].strip()
            int(config["TOPIC_ID"])
        except ValueError:
            raise ValueError(
                f"TOPIC_ID must be a valid integer, got: {config['TOPIC_ID']!r}"
            )

    if config["USER_ID"]:
        try:
            int(config["USER_ID"])
        except ValueError:
            raise ValueError(
                f"USER_ID must be a valid integer, got: {config['USER_ID']!r}"
            )

    logger.info(f"Loaded config: {config}")
    return config


def load_sites() -> List[SiteConfig]:
    """Load list of websites to monitor from data/sites.json."""
    sites_path = os.path.join(os.path.dirname(__file__), "data", "sites.json")
    try:
        with open(sites_path, "r") as file:
            sites = json.load(file)
            logger.info(f"Loaded sites: {sites}")
            for site in sites:
                if not isinstance(site, dict) or "url" not in site:
                    raise ValueError(f"Invalid site entry: {site}")
                # Ensure notifications fields exist
                site.setdefault("domain_notifications", [])
                site.setdefault("ssl_notifications", [])
            return sites
    except FileNotFoundError as e:
        logger.error(f"{sites_path} not found")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {sites_path}: {e}")
        raise


def save_sites(sites: List[SiteConfig]):
    """Save updated sites to data/sites.json."""
    sites_path = os.path.join(os.path.dirname(__file__), "data", "sites.json")
    try:
        with open(sites_path, "w") as file:
            json.dump(sites, file, indent=2)
        logger.info("Saved updated sites to data/sites.json")
    except Exception as e:
        logger.error(f"Failed to save sites to {sites_path}: {e}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def check_website_status(url: str) -> WebsiteStatus:
    """Check the status of a website with retries."""
    result: WebsiteStatus = {"url": url, "status": "unknown", "error": None}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                result["status"] = f"{response.status} {response.reason}"
                logger.debug(f"Website {url} - Status: {result['status']}")
                return result
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "down"
        logger.warning(f"Website check failed: {url} - {e}")
        return result


def check_ssl_certificate_manual(hostname: str, port: int = 443) -> SSLStatus:
    """Check SSL certificate status using ssl.SSLSocket."""
    result: SSLStatus = {
        "url": f"https://{hostname}",
        "ssl_status": "unknown",
        "expires": None,
        "error": None,
    }

    try:
        context = ssl.create_default_context(cafile=certifi.where())
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                logger.debug(f"SSL cert for {hostname}: {cert}")
                if cert:
                    expires = datetime.strptime(
                        cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                    )
                    result["ssl_status"] = "valid"
                    result["expires"] = expires.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    result["ssl_status"] = "no_ssl"
                    result["error"] = "No certificate provided"
                logger.debug(
                    f"SSL check for {hostname}: {result['ssl_status']}"
                )
    except Exception as e:
        result["error"] = str(e)
        result["ssl_status"] = "invalid"
        logger.warning(f"SSL check failed for {hostname}: {e}")

    return result


async def check_ssl_certificate(url: str) -> SSLStatus:
    """Check SSL certificate status for a website."""
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    port = parsed_url.port or 443

    if not hostname:
        return {
            "url": url,
            "ssl_status": "invalid",
            "expires": None,
            "error": "Invalid URL",
        }

    return check_ssl_certificate_manual(hostname, port)


def check_domain_expiration(domain: str) -> DomainStatus:
    """Check domain expiration date using WHOIS."""
    result: DomainStatus = {
        "url": domain,
        "expires": None,
        "error": None,
    }

    try:
        w = whois.whois(domain)
        if isinstance(w.expiration_date, list):
            expiration_date = w.expiration_date[0]
        else:
            expiration_date = w.expiration_date

        if expiration_date:
            if isinstance(expiration_date, datetime):
                result["expires"] = expiration_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                result["error"] = "Invalid expiration date format"
        else:
            result["error"] = "No expiration date found"
        logger.debug(f"Domain {domain}: {result['expires']}")
    except Exception as e:
        logger.error(f"Domain check failed for {domain}: {e}")
        result["error"] = str(e)

    return result


def get_nearest_threshold(
    days_left: int, thresholds: List[int]
) -> Optional[int]:
    """Find the nearest threshold that matches the days left."""
    for threshold in sorted(thresholds, reverse=True):
        if days_left <= threshold:
            return threshold
    return None


async def send_notification(bot: Bot, config: Dict[str, any], message: str):
    """Send notification based on NOTIFICATION_MODE."""
    try:
        if config["NOTIFICATION_MODE"] == "group":
            await bot.send_message(
                chat_id=config["GROUP_ID"],
                message_thread_id=(
                    int(config["TOPIC_ID"]) if config["TOPIC_ID"] else None
                ),
                text=message,
            )
        else:  # user
            await bot.send_message(
                chat_id=config["USER_ID"],
                text=message,
            )
        logger.info(f"Sent notification: {message}")
    except TelegramBadRequest as e:
        logger.error(f"Failed to send notification: {e}")


async def monitor_websites(bot: Bot, config: Dict[str, any], interval: int):
    """Periodically monitor websites and send notifications if issues are found."""
    logger.info("Starting website monitoring task")
    try:
        sites = load_sites()
        last_status: Dict[str, tuple[WebsiteStatus, SSLStatus]] = {}
        domain_thresholds = config["DOMAIN_EXPIRY_THRESHOLD"]
        ssl_thresholds = config["SSL_EXPIRY_THRESHOLD"]
    except Exception as e:
        logger.error(f"Failed to load sites or config: {e}")
        return

    while True:
        logger.info(f"Checking {len(sites)} sites")
        tasks = []
        for site in sites:
            url = site["url"]
            tasks.append(check_website_status(url))
            tasks.append(check_ssl_certificate(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, site in enumerate(sites):
            url = site["url"]
            status_result = results[i * 2]
            ssl_result = results[i * 2 + 1]

            if isinstance(status_result, Exception) or isinstance(
                ssl_result, Exception
            ):
                logger.error(
                    f"Error checking {url}: {status_result or ssl_result}"
                )
                continue

            logger.info(
                f"Checked {url}: Status={status_result['status']}, SSL={ssl_result['ssl_status']}"
            )

            # Update SSL data
            site["ssl_valid"] = ssl_result["ssl_status"] == "valid"
            site["ssl_expires"] = ssl_result["expires"]

            # Check SSL expiration warnings
            if site["ssl_expires"]:
                try:
                    ssl_expiry = datetime.strptime(
                        site["ssl_expires"], "%Y-%m-%d %H:%M:%S"
                    )
                    days_left = (ssl_expiry - datetime.now()).days
                    nearest_threshold = get_nearest_threshold(
                        days_left, ssl_thresholds
                    )
                    if (
                        nearest_threshold
                        and nearest_threshold not in site["ssl_notifications"]
                    ):
                        message = (
                            f"⚠️ SSL expiration warning!\n"
                            f"URL: {url}\n"
                            f"Expires: {site['ssl_expires']}\n"
                            f"Days left: {days_left}"
                        )
                        await send_notification(bot, config, message)
                        site["ssl_notifications"].append(nearest_threshold)
                except ValueError:
                    logger.error(f"Invalid ssl_expires format for {url}")

            # Check domain expiration if not checked recently
            parsed_url = urlparse(url)
            domain = parsed_url.hostname
            last_checked = site.get("domain_last_checked")
            should_check_domain = True

            if last_checked:
                try:
                    last_checked_dt = datetime.strptime(
                        last_checked, "%Y-%m-%d %H:%M:%S"
                    )
                    if datetime.now() - last_checked_dt < timedelta(days=1):
                        should_check_domain = False
                except ValueError:
                    logger.warning(
                        f"Invalid domain_last_checked format for {url}"
                    )

            if should_check_domain and domain:
                domain_result = check_domain_expiration(domain)
                site["domain_expires"] = domain_result["expires"]
                site["domain_last_checked"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if domain_result["error"]:
                    logger.warning(
                        f"Domain expiration check failed for {url}: {domain_result['error']}"
                    )

            # Check domain expiration warnings
            if site["domain_expires"]:
                try:
                    domain_expiry = datetime.strptime(
                        site["domain_expires"], "%Y-%m-%d %H:%M:%S"
                    )
                    days_left = (domain_expiry - datetime.now()).days
                    nearest_threshold = get_nearest_threshold(
                        days_left, domain_thresholds
                    )
                    if (
                        nearest_threshold
                        and nearest_threshold
                        not in site["domain_notifications"]
                    ):
                        message = (
                            f"⚠️ Domain expiration warning!\n"
                            f"URL: {url}\n"
                            f"Expires: {site['domain_expires']}\n"
                            f"Days left: {days_left}"
                        )
                        await send_notification(bot, config, message)
                        site["domain_notifications"].append(nearest_threshold)
                except ValueError:
                    logger.error(f"Invalid domain_expires format for {url}")

            current_status = (status_result, ssl_result)
            last_site_status = last_status.get(url)

            if last_site_status != current_status:
                try:
                    if (
                        status_result["error"]
                        or "200" not in status_result["status"]
                    ):
                        message = (
                            f"⚠️ Website issue detected!\n"
                            f"URL: {url}\n"
                            f"Status: {status_result['status']}\n"
                            f"Error: {status_result['error'] or 'N/A'}"
                        )
                        await send_notification(bot, config, message)
                        logger.warning(
                            f"Sent website issue notification for {url}: {status_result['status']}"
                        )

                    if (
                        ssl_result["error"]
                        or ssl_result["ssl_status"] != "valid"
                    ):
                        message = (
                            f"⚠️ SSL issue detected!\n"
                            f"URL: {url}\n"
                            f"SSL Status: {ssl_result['ssl_status']}\n"
                            f"Expires: {ssl_result['expires'] or 'N/A'}\n"
                            f"Error: {ssl_result['error'] or 'N/A'}"
                        )
                        await send_notification(bot, config, message)
                        logger.warning(
                            f"Sent SSL issue notification for {url}: {ssl_result['ssl_status']}"
                        )

                    last_status[url] = current_status
                except TelegramBadRequest as e:
                    logger.error(f"Failed to send notification: {e}")

        # Save updated sites
        save_sites(sites)

        await asyncio.sleep(interval)


@router.message(Command("start"))
async def start_command(message: Message):
    """Handle /start command."""
    logger.info("Received /start command")
    await message.answer(
        "Website Monitoring Bot started!\n"
        "Use /status to check current website statuses."
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Handle /status command to report current status of all websites."""
    logger.info("Received /status command")
    try:
        sites = load_sites()
        config = load_config()
        response = "Current website statuses:\n\n"
        logger.info(f"Checking status for {len(sites)} sites")

        tasks = []
        for site in sites:
            url = site["url"]
            tasks.append(check_website_status(url))
            tasks.append(check_ssl_certificate(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, site in enumerate(sites):
            url = site["url"]
            status_result = results[i * 2]
            ssl_result = results[i * 2 + 1]

            if isinstance(status_result, Exception) or isinstance(
                ssl_result, Exception
            ):
                response += f"🌐 {url}\nError during check\n\n"
                logger.error(f"Error checking {url} for status command")
                continue

            # Update SSL data
            site["ssl_valid"] = ssl_result["ssl_status"] == "valid"
            site["ssl_expires"] = ssl_result["expires"]

            # Check domain expiration if not checked recently
            parsed_url = urlparse(url)
            domain = parsed_url.hostname
            last_checked = site.get("domain_last_checked")
            should_check_domain = True

            if last_checked:
                try:
                    last_checked_dt = datetime.strptime(
                        last_checked, "%Y-%m-%d %H:%M:%S"
                    )
                    if datetime.now() - last_checked_dt < timedelta(days=1):
                        should_check_domain = False
                except ValueError:
                    logger.warning(
                        f"Invalid domain_last_checked format for {url}"
                    )

            if should_check_domain and domain:
                domain_result = check_domain_expiration(domain)
                site["domain_expires"] = domain_result["expires"]
                site["domain_last_checked"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if domain_result["error"]:
                    logger.warning(
                        f"Domain expiration check failed for {url}: {domain_result['error']}"
                    )

            # Calculate days left for SSL and domain expiration
            ssl_days_left = "N/A"
            if site["ssl_expires"]:
                try:
                    ssl_expiry = datetime.strptime(
                        site["ssl_expires"], "%Y-%m-%d %H:%M:%S"
                    )
                    ssl_days_left = (ssl_expiry - datetime.now()).days
                except ValueError:
                    logger.error(f"Invalid ssl_expires format for {url}")

            domain_days_left = "N/A"
            if site["domain_expires"]:
                try:
                    domain_expiry = datetime.strptime(
                        site["domain_expires"], "%Y-%m-%d %H:%M:%S"
                    )
                    domain_days_left = (domain_expiry - datetime.now()).days
                except ValueError:
                    logger.error(f"Invalid domain_expires format for {url}")

            response += (
                f"🌐 {url}\n"
                f"Status: {status_result['status']}\n"
                f"SSL Valid: {site['ssl_valid']}\n"
                f"SSL Expires: {site['ssl_expires'] or 'N/A'}\n"
                f"SSL Days Left: {ssl_days_left}\n"
                f"Domain Expires: {site['domain_expires'] or 'N/A'}\n"
                f"Domain Days Left: {domain_days_left}\n\n"
            )
            logger.info(
                f"Status for {url}: Status={status_result['status']}, SSL={ssl_result['ssl_status']}, Domain={site['domain_expires']}"
            )

        # Save updated sites
        save_sites(sites)

        await message.answer(response)
        logger.info("Sent status response")
    except Exception as e:
        logger.error(f"Status command failed: {e}")
        await message.answer(
            "Error retrieving statuses. Check logs for details."
        )


async def main():
    """Main function to initialize and run the bot."""
    try:
        config = load_config()
        bot = Bot(token=config["BOT_TOKEN"])
        dp = Dispatcher()

        # Set bot commands
        await bot.set_my_commands(
            [
                BotCommand(
                    command="start", description="Start website monitoring"
                ),
                BotCommand(
                    command="status",
                    description="Check current website statuses",
                ),
            ]
        )
        logger.info("Bot commands set")

        dp.include_router(router)

        # Clear any existing webhook to avoid conflicts
        await bot.delete_webhook()
        logger.info("Webhook cleared")

        # Start monitoring task
        asyncio.create_task(
            monitor_websites(
                bot,
                config,
                int(config["CHECK_INTERVAL"]),
            )
        )

        # Start polling
        await dp.start_polling(bot)
    except TelegramConflictError as e:
        logger.error(
            f"Conflict error: {e}. Ensure only one bot instance is running."
        )
        raise
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
