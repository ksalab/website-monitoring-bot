import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
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


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Args:
        text: Text to escape.

    Returns:
        str: Escaped text.
    """
    if text is None or text == "":
        return "N/A"
    special_chars = r'._!#$%&*+-=|\:;<>?@[]^{}()~`'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


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
                    response = (
                        f"🌐 {escape_markdown_v2(url)}\n"
                        f"Status: 🔴 Error during check\n"
                        f"--- SSL ---\n"
                        f"Error: Check failed\n"
                        f"--- Domain ---\n"
                        f"Error: Check failed\n"
                    )
                    logger.debug(
                        f"Sending /status message for {url}:\n{response}"
                    )
                    await message.answer(response, parse_mode="MarkdownV2")
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
                registrar_info = "Unknown"
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
                                registrar_info = f"[{escape_markdown_v2(registrar)}]({escape_markdown_v2(registrar_url)})"
                            else:
                                registrar_info = escape_markdown_v2(registrar)
                    else:
                        domain_status = f"WHOIS error: {escape_markdown_v2(domain_result['error'])}"
                        if site["domain_expires"]:
                            try:
                                domain_expiry = datetime.strptime(
                                    site["domain_expires"], DATE_FORMAT
                                )
                                domain_days_left = (
                                    domain_expiry - datetime.now()
                                ).days
                                domain_status += f" \\(Last checked: {escape_markdown_v2(site['domain_last_checked'] or 'N/A')}, Expires: {escape_markdown_v2(site['domain_expires'])}\\)"
                            except ValueError:
                                domain_status += f" \\(Last checked: {escape_markdown_v2(site['domain_last_checked'] or 'N/A')}, Invalid date\\)"
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

                # Build response with explicit escaping
                response = (
                    f"🌐 {escape_markdown_v2(url)}\n"
                    f"Status: {status_emoji} {escape_markdown_v2(status_result['status'])}\n"
                    f"--- SSL ---\n"
                    f"Valid: {site['ssl_valid']}\n"
                    f"Expires: {escape_markdown_v2(site['ssl_expires'] or 'N/A')}\n"
                    f"Days Left: {ssl_days_left}\n"
                    f"--- Domain ---\n"
                    f"Expires: {domain_status}\n"
                    f"Days Left: {domain_days_left}\n"
                    f"Registrar: {escape_markdown_v2(registrar_info)}\n"
                )

                try:
                    logger.debug(
                        f"Sending /status message for {url}:\n{response}"
                    )
                    await message.answer(response, parse_mode="MarkdownV2")
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

        response = "Monitored websites:\n\n"
        for site in sites:
            response += f"- {site['url']}\n"
        await message.answer(response)
        logger.info(
            f"Sent /listsites response with {len(sites)} sites to chat_id={user_id}"
        )
    except Exception as e:
        logger.error(f"/listsites command failed for user_id={user_id}: {e}")
        await message.answer(
            "Error retrieving site list. Check logs for details."
        )
