import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from urllib.parse import urlparse
from aiogram.utils.formatting import (
    Text,
    Bold,
    Url,
    as_line,
    as_marked_section,
    as_key_value,
)
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
    user_id = message.chat.id
    logger.info("Received /status command from chat_id=%s", user_id)
    try:
        sites = load_sites(user_id)
        if not sites:
            await message.answer("No sites are currently monitored.")
            logger.info(f"Sent empty /status response to chat_id={user_id}")
            return

        logger.info(
            f"Processing status for {len(sites)} sites for user_id={user_id}"
        )

        tasks = []
        for site in sites:
            url = site["url"]
            tasks.append(check_website_status(url))
            tasks.append(check_ssl_certificate(url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, site in enumerate(sites):
            url = site["url"]
            try:
                status_result = results[i * 2]
                ssl_result = results[i * 2 + 1]

                if isinstance(status_result, Exception) or isinstance(
                    ssl_result, Exception
                ):
                    content = (as_line(Text("🌐 ", url)),)
                    as_line(Text("Status: 🔴 Error during check")),
                    as_marked_section(
                        "--- SSL ---", as_key_value("Error:", "Check failed")
                    ),
                    as_marked_section(
                        "--- Domain ---",
                        as_key_value("Error:", "Check failed"),
                    )
                    logger.debug(
                        f"Sending /status message for {url}: {content.render()}"
                    )
                    await message.answer(**content.as_kwargs())
                    logger.error(
                        f"Error checking {url} for /status command: {status_result or ssl_result}"
                    )
                    continue

                # Update SSL data
                site["ssl_valid"] = ssl_result["ssl_status"] == "valid"
                site["ssl_expires"] = ssl_result["expires"]

                # Determine status emoji
                status_emoji = (
                    "🟢" if "200" in status_result["status"] else "🔴"
                )

                # Log fields before building response
                logger.debug(
                    f"Building /status for {url}: "
                    f"url={url}, status={status_result['status']}, "
                    f"ssl_valid={site['ssl_valid']}, ssl_expires={site['ssl_expires']}"
                )

                # Always perform WHOIS check for /status
                parsed_url = urlparse(url)
                domain = parsed_url.hostname
                domain_status = "Unknown"
                domain_days_left = "N/A"
                registrar_info = Text("Unknown")
                if domain:
                    domain_result = check_domain_expiration(domain)
                    logger.debug(
                        f"WHOIS for {domain}: success={domain_result['success']}, "
                        f"expires={domain_result['expires']}, registrar={domain_result['registrar']}, "
                        f"registrar_url={domain_result['registrar_url']}, error={domain_result['error']}"
                    )
                    if domain_result["success"]:
                        site["domain_expires"] = domain_result["expires"]
                        site["domain_last_checked"] = datetime.now().strftime(
                            DATE_FORMAT
                        )
                        domain_status = site["domain_expires"] or "N/A"
                        if site["domain_expires"]:
                            try:
                                domain_expiry = datetime.strptime(
                                    site["domain_expires"], DATE_FORMAT
                                )
                                domain_days_left = (
                                    domain_expiry - datetime.now()
                                ).days
                            except ValueError:
                                logger.error(
                                    f"Invalid domain_expires format for {url}: {site['domain_expires']}"
                                )
                                domain_status = "Invalid date format"
                        # Registrar info
                        registrar = domain_result["registrar"]
                        registrar_url = domain_result["registrar_url"]
                        if registrar:
                            if (
                                isinstance(registrar_url, list)
                                and registrar_url
                            ):
                                registrar_url = registrar_url[0]
                            if registrar_url:
                                registrar_info = Text(
                                    "[",
                                    registrar,
                                    "](",
                                    Url(registrar_url),
                                    ")",
                                )
                            else:
                                registrar_info = Text(registrar)
                    else:
                        domain_status = Text(
                            "WHOIS error: ", domain_result["error"]
                        )
                        if site["domain_expires"]:
                            try:
                                domain_expiry = datetime.strptime(
                                    site["domain_expires"], DATE_FORMAT
                                )
                                domain_days_left = (
                                    domain_expiry - datetime.now()
                                ).days
                                domain_status = Text(
                                    domain_status,
                                    " (Last checked: ",
                                    site["domain_last_checked"] or "N/A",
                                    ", Expires: ",
                                    site["domain_expires"],
                                    ")",
                                )
                            except ValueError:
                                domain_status = Text(
                                    domain_status,
                                    " (Last checked: ",
                                    site["domain_last_checked"] or "N/A",
                                    ", Invalid date)",
                                )
                                logger.error(
                                    f"Invalid domain_expires format for {url}: {site['domain_expires']}"
                                )

                # Calculate SSL days left
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

                # Build response with aiogram formatting
                content = (as_line(Text("🌐 ", url)),)
                as_line(
                    Text(
                        "Status: ", status_emoji, " ", status_result["status"]
                    )
                ),
                as_marked_section(
                    "--- SSL ---",
                    as_key_value("Valid: ", str(site["ssl_valid"])),
                    as_key_value("Expires: ", site["ssl_expires"] or "N/A"),
                    as_key_value("Days Left: ", str(ssl_days_left)),
                ),
                as_marked_section(
                    "--- Domain ---",
                    as_key_value("Expires: ", domain_status),
                    as_key_value("Days Left: ", str(domain_days_left)),
                    as_key_value("Registrar: ", registrar_info),
                )

                try:
                    text, entities = content.render()
                    logger.debug(
                        f"Sending /status message for {url}: text={text}, entities={entities}"
                    )
                    await message.answer(**content.as_kwargs())
                    logger.info(
                        f"Sent /status response for {url} to chat_id={user_id}"
                    )
                except TelegramBadRequest as e:
                    logger.error(
                        f"Failed to send /status message for {url} to chat_id={user_id}: {e}"
                    )
                    await message.answer(
                        f"Error sending status for {url}. Check logs for details."
                    )

                logger.info(
                    f"Status processed for {url}: Status={status_result['status']}, "
                    f"SSL_Expires={site['ssl_expires']}, Domain_Expires={domain_status}, "
                    f"Registrar={registrar_info}"
                )

            except Exception as e:
                logger.error(
                    f"Error processing status for {url} for user_id={user_id}: {e}"
                )
                await message.answer(
                    f"Error processing status for {url}. Check logs for details."
                )

        save(user_id, sites)
    except Exception as e:
        logger.error(f"/status command failed for user_id={user_id}: {e}")
        await message.answer(
            "Error retrieving statuses. Check logs for details."
        )


@router.message(Command("listsites"))
async def listsites_command(message: Message):
    """Handle /listsites command to list all monitored websites."""
    user_id = message.chat.id
    logger.info("Received /listsites command from chat_id=%s", user_id)
    try:
        sites = load_sites(user_id)
        if not sites:
            await message.answer("No sites are currently monitored.")
            logger.info(f"Sent empty /listsites response to chat_id={user_id}")
            return

        content = Text("Monitored websites:\n\n")
        for site in sites:
            content += Text("- ", site["url"], "\n")
        await message.answer(**content.as_kwargs())
        logger.info(
            f"Sent /listsites response with {len(sites)} sites to chat_id={user_id}"
        )
    except Exception as e:
        logger.error(f"/listsites command failed for user_id={user_id}: {e}")
        await message.answer(
            "Error retrieving site list. Check logs for details."
        )
