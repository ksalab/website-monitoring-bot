import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from urllib.parse import urlparse
from .storage import SiteConfig, load_sites, save
from .checks import (
    check_website_status,
    check_ssl_certificate,
    check_domain_expiration,
)
from .config import DATE_FORMAT

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def start_command(message: Message):
    """Handle /start command."""
    logger.info("Received /start command from chat_id=%s", message.chat.id)
    await message.answer(
        "Website Monitoring Bot started!\n"
        "Use /status to check current website statuses or /listsites to list monitored sites."
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Handle /status command to report current status of all websites."""
    logger.info("Received /status command from chat_id=%s", message.chat.id)
    try:
        sites = load_sites()
        response = "Current website statuses:\n\n"
        logger.info(f"Processing status for {len(sites)} sites")

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
                logger.error(
                    f"Error checking {url} for /status command: {status_result or ssl_result}"
                )
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
                        last_checked, DATE_FORMAT
                    )
                    if datetime.now() - last_checked_dt < timedelta(days=1):
                        should_check_domain = False
                        logger.debug(
                            f"Skipping domain check for {url}: Last checked {last_checked}"
                        )
                except ValueError:
                    logger.warning(
                        f"Invalid domain_last_checked format for {url}: {last_checked}"
                    )

            if should_check_domain and domain:
                domain_result = check_domain_expiration(domain)
                site["domain_expires"] = domain_result["expires"]
                site["domain_last_checked"] = datetime.now().strftime(
                    DATE_FORMAT
                )
                if domain_result["error"]:
                    logger.warning(
                        f"Domain expiration check failed for {url}: {domain_result['error']}"
                    )

            # Calculate days left
            ssl_days_left = "N/A"
            if site["ssl_expires"]:
                try:
                    ssl_expiry = datetime.strptime(
                        site["ssl_expires"], DATE_FORMAT
                    )
                    ssl_days_left = (ssl_expiry - datetime.now()).days
                except ValueError:
                    logger.error(
                        f"Invalid ssl_expires format for {url}: {site['ssl_expires']}"
                    )

            domain_days_left = "N/A"
            if site["domain_expires"]:
                try:
                    domain_expiry = datetime.strptime(
                        site["domain_expires"], DATE_FORMAT
                    )
                    domain_days_left = (domain_expiry - datetime.now()).days
                except ValueError:
                    logger.error(
                        f"Invalid domain_expires format for {url}: {site['domain_expires']}"
                    )

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
                f"Status processed for {url}: Status={status_result['status']}, SSL_Expires={site['ssl_expires']}, Domain_Expires={site['domain_expires']}"
            )

        save(sites)
        await message.answer(response)
        logger.info(f"Sent /status response to chat_id={message.chat.id}")
    except Exception as e:
        logger.error(f"/status command failed: {e}")
        await message.answer(
            "Error retrieving statuses. Check logs for details."
        )


@router.message(Command("listsites"))
async def listsites_command(message: Message):
    """Handle /listsites command to list all monitored websites."""
    logger.info("Received /listsites command from chat_id=%s", message.chat.id)
    try:
        sites = load_sites()
        if not sites:
            await message.answer("No sites are currently monitored.")
            logger.info(
                "Sent empty /listsites response to chat_id=%s", message.chat.id
            )
            return

        response = "Monitored websites:\n\n"
        for site in sites:
            response += f"- {site['url']}\n"
        await message.answer(response)
        logger.info(
            f"Sent /listsites response with {len(sites)} sites to chat_id={message.chat.id}"
        )
    except Exception as e:
        logger.error(f"/listsites command failed: {e}")
        await message.answer(
            "Error retrieving site list. Check logs for details."
        )
