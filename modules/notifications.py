import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from urllib.parse import urlparse
from .storage import SiteConfig, load_sites, save
from .checks import (
    WebsiteStatus,
    SSLStatus,
    check_website_status,
    check_ssl_certificate,
    check_domain_expiration,
)
from .config import DATA_DIR, DATE_FORMAT

logger = logging.getLogger(__name__)


async def send_notification(
    bot: Bot, config: Dict[str, any], message: str
) -> None:
    """Send notification based on configuration mode.

    Args:
        bot: Telegram Bot instance.
        config: Configuration dictionary.
        message: Notification message to send.
    """
    logger.debug(f"Sending notification: {message}")
    try:
        if config["NOTIFICATION_MODE"] == "group":
            await bot.send_message(
                chat_id=config["GROUP_ID"],
                message_thread_id=(
                    int(config["TOPIC_ID"]) if config["TOPIC_ID"] else None
                ),
                text=message,
            )
            logger.info(
                f"Notification sent to group {config['GROUP_ID']} (topic: {config['TOPIC_ID'] or 'none'}): {message}"
            )
        else:  # user
            await bot.send_message(
                chat_id=config["USER_ID"],
                text=message,
            )
            logger.info(
                f"Notification sent to user {config['USER_ID']}: {message}"
            )
    except TelegramBadRequest as e:
        logger.error(f"Failed to send notification: {e}")


def get_nearest_threshold(
    days_left: int, thresholds: List[int]
) -> Optional[int]:
    """Find the nearest threshold that matches the days left.

    Args:
        days_left: Number of days until expiration.
        thresholds: List of threshold days.

    Returns:
        Optional[int]: Nearest threshold or None if no match.
    """
    logger.debug(
        f"Finding nearest threshold for {days_left} days, thresholds={thresholds}"
    )
    for threshold in sorted(thresholds, reverse=True):
        if days_left <= threshold:
            logger.debug(f"Selected threshold: {threshold}")
            return threshold
    logger.debug("No matching threshold found")
    return None


def get_user_ids() -> List[int]:
    """Get list of user IDs based on files in data/ directory.

    Returns:
        List[int]: List of user IDs.
    """
    logger.debug(f"Scanning {DATA_DIR} for user site files")
    user_ids = []
    if not os.path.exists(DATA_DIR):
        logger.info(f"Data directory {DATA_DIR} does not exist")
        return user_ids

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            try:
                user_id = int(filename[:-5])  # Remove .json
                user_ids.append(user_id)
            except ValueError:
                logger.warning(f"Invalid filename in data/: {filename}")
    logger.info(f"Found {len(user_ids)} user IDs: {user_ids}")
    return user_ids


async def check_site_status(
    user_id: int,
    site: SiteConfig,
    config: Dict[str, any],
    bot: Bot,
    last_status: Dict[str, Tuple[WebsiteStatus, SSLStatus]],
) -> None:
    """Check site status and send notifications if needed.

    Args:
        user_id: Telegram user or chat ID.
        site: Site configuration.
        config: Bot configuration.
        bot: Telegram Bot instance.
        last_status: Dictionary storing last known status.
    """
    url = site["url"]
    logger.debug(f"Processing site {url} for user_id={user_id}")

    status_result = await check_website_status(url)
    ssl_result = await check_ssl_certificate(url)

    if isinstance(status_result, Exception) or isinstance(
        ssl_result, Exception
    ):
        logger.error(
            f"Error checking {url} for user_id={user_id}: {status_result or ssl_result}"
        )
        return

    logger.info(
        f"Check completed for {url} (user_id={user_id}): Status={status_result['status']}, SSL={ssl_result['ssl_status']}"
    )

    # Update SSL data
    site["ssl_valid"] = ssl_result["ssl_status"] == "valid"
    site["ssl_expires"] = ssl_result["expires"]

    # Check SSL expiration warnings
    if site["ssl_expires"]:
        try:
            ssl_expiry = datetime.strptime(site["ssl_expires"], DATE_FORMAT)
            days_left = (ssl_expiry - datetime.now()).days
            nearest_threshold = get_nearest_threshold(
                days_left, config["SSL_EXPIRY_THRESHOLD"]
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
            logger.error(
                f"Invalid ssl_expires format for {url} (user_id={user_id}): {site['ssl_expires']}"
            )

    # Check domain expiration if not checked recently
    parsed_url = urlparse(url)
    domain = parsed_url.hostname
    last_checked = site.get("domain_last_checked")
    should_check_domain = True

    if last_checked:
        try:
            last_checked_dt = datetime.strptime(last_checked, DATE_FORMAT)
            if datetime.now() - last_checked_dt < timedelta(days=1):
                should_check_domain = False
                logger.debug(
                    f"Skipping domain check for {url} (user_id={user_id}): Last checked {last_checked}"
                )
        except ValueError:
            logger.warning(
                f"Invalid domain_last_checked format for {url} (user_id={user_id}): {last_checked}"
            )
            should_check_domain = True

    if should_check_domain and domain:
        domain_result = check_domain_expiration(domain)
        if domain_result["success"]:
            site["domain_expires"] = domain_result["expires"]
            site["domain_last_checked"] = datetime.now().strftime(DATE_FORMAT)
            logger.info(
                f"Updated domain info for {url} (user_id={user_id}): Expires={site['domain_expires']}"
            )
        else:
            logger.warning(
                f"Domain expiration check failed for {url} (user_id={user_id}): {domain_result['error']}"
            )

    # Check domain expiration warnings
    if site["domain_expires"]:
        try:
            domain_expiry = datetime.strptime(
                site["domain_expires"], DATE_FORMAT
            )
            days_left = (domain_expiry - datetime.now()).days
            nearest_threshold = get_nearest_threshold(
                days_left, config["DOMAIN_EXPIRY_THRESHOLD"]
            )
            if (
                nearest_threshold
                and nearest_threshold not in site["domain_notifications"]
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
            logger.error(
                f"Invalid domain_expires format for {url} (user_id={user_id}): {site['domain_expires']}"
            )

    current_status = (status_result, ssl_result)
    status_key = f"{user_id}:{url}"  # Unique key per user and URL
    last_site_status = last_status.get(status_key)

    if last_site_status != current_status:
        try:
            if status_result["error"] or "200" not in status_result["status"]:
                message = (
                    f"⚠️ Website issue detected!\n"
                    f"URL: {url}\n"
                    f"Status: {status_result['status']}\n"
                    f"Error: {status_result['error'] or 'N/A'}"
                )
                await send_notification(bot, config, message)
                logger.warning(
                    f"Website issue notification sent for {url} (user_id={user_id}): Status={status_result['status']}, Error={status_result['error']}"
                )

            if ssl_result["error"] or ssl_result["ssl_status"] != "valid":
                message = (
                    f"⚠️ SSL issue detected!\n"
                    f"URL: {url}\n"
                    f"SSL Status: {ssl_result['ssl_status']}\n"
                    f"Expires: {ssl_result['expires'] or 'N/A'}\n"
                    f"Error: {ssl_result['error'] or 'N/A'}"
                )
                await send_notification(bot, config, message)
                logger.warning(
                    f"SSL issue notification sent for {url} (user_id={user_id}): SSL_Status={ssl_result['ssl_status']}, Error={ssl_result['error']}"
                )

            last_status[status_key] = current_status
            logger.debug(f"Updated last status for {url} (user_id={user_id})")
        except TelegramBadRequest as e:
            logger.error(
                f"Failed to send notification for {url} (user_id={user_id}): {e}"
            )


async def monitor_websites(
    bot: Bot, config: Dict[str, any], interval: int
) -> None:
    """Periodically monitor websites for all users and send notifications.

    Args:
        bot: Telegram Bot instance.
        config: Configuration dictionary.
        interval: Check interval in seconds.
    """
    logger.info("Starting website monitoring task")
    try:
        last_status: Dict[str, Tuple[WebsiteStatus, SSLStatus]] = {}
        logger.debug(
            f"Monitoring configuration: interval={interval}s, domain_thresholds={config['DOMAIN_EXPIRY_THRESHOLD']}, ssl_thresholds={config['SSL_EXPIRY_THRESHOLD']}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize monitoring: {e}")
        return

    while True:
        logger.info("Starting check cycle for all users")
        user_ids = get_user_ids()
        if not user_ids:
            logger.info("No users found, skipping check cycle")
            await asyncio.sleep(interval)
            continue

        for user_id in user_ids:
            try:
                sites = load_sites(user_id)
                if not sites:
                    logger.debug(f"No sites to monitor for user_id={user_id}")
                    continue

                logger.info(
                    f"Checking {len(sites)} sites for user_id={user_id}"
                )
                for site in sites:
                    await check_site_status(
                        user_id, site, config, bot, last_status
                    )

                save(user_id, sites)
            except Exception as e:
                logger.error(
                    f"Error processing sites for user_id={user_id}: {e}"
                )

        logger.info(f"Check cycle completed, sleeping for {interval} seconds")
        await asyncio.sleep(interval)
