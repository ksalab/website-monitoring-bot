import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from urllib.parse import urlparse, urlunparse
from aiogram.utils.formatting import (
    Text,
    as_line,
    as_list,
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


# Определение FSM для добавления сайта
class AddSiteState(StatesGroup):
    url = State()


@router.message(CommandStart())
async def start_command(message: Message):
    """Handle /start command."""
    logger.info("Received /start command from chat_id=%s", message.chat.id)
    await message.answer(
        "Website Monitoring Bot started!\n"
        "Use /status to check current website statuses, /listsites to list monitored sites, or /addsite <url> to add a new site."
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
                    content = as_list(
                        as_line(Text("🌐 ", url)),
                        as_line(Text("Status: 🔴 Error during check")),
                        as_marked_section(
                            "--- SSL ---",
                            as_key_value("Error", "Check failed"),
                        ),
                        as_marked_section(
                            "--- Domain ---",
                            as_key_value("Error", "Check failed"),
                        ),
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
                                    registrar,
                                    entities=[
                                        {
                                            "type": "text_link",
                                            "url": registrar_url,
                                        }
                                    ],
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
                content = as_list(
                    as_line(Text("🌐 ", url)),
                    as_line(
                        Text(
                            "Status: ",
                            status_emoji,
                            " ",
                            status_result["status"],
                        )
                    ),
                    as_marked_section(
                        "--- SSL ---",
                        as_key_value("Valid", str(site["ssl_valid"])),
                        as_key_value("Expires", site["ssl_expires"] or "N/A"),
                        as_key_value("Days Left", str(ssl_days_left)),
                    ),
                    as_marked_section(
                        "--- Domain ---",
                        as_key_value("Expires", domain_status),
                        as_key_value("Days Left", str(domain_days_left)),
                        as_key_value("Registrar", registrar_info),
                    ),
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
            await message.answer(
                "No sites are currently monitored. Use /addsite <url> to add a new site."
            )
            logger.info(f"Sent empty /listsites response to chat_id={user_id}")
            return

        content = Text("Monitored websites:\n\n")
        for site in sites:
            content += Text("- ", site["url"], "\n")

        # Add inline button
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Add site", callback_data="add_site"
                    )
                ]
            ]
        )

        await message.answer(**content.as_kwargs(), reply_markup=keyboard)
        logger.info(
            f"Sent /listsites response with {len(sites)} sites to chat_id={user_id}"
        )
    except Exception as e:
        logger.error(f"/listsites command failed for user_id={user_id}: {e}")
        await message.answer(
            "Error retrieving site list. Check logs for details."
        )


@router.callback_query(lambda c: c.data == "add_site")
async def add_site_callback(callback_query: CallbackQuery, state: FSMContext):
    """Handle 'Add site' button callback."""
    logger.info(
        f"Received add_site callback from user_id={callback_query.from_user.id}"
    )
    await callback_query.message.answer(
        "Please enter the URL of the new site (e.g., https://example.com)."
    )
    await state.set_state(AddSiteState.url)
    await callback_query.answer()


@router.message(AddSiteState.url, F.text)
async def process_add_site_url(message: Message, state: FSMContext):
    """Process URL input for adding a new site."""
    user_id = message.chat.id
    logger.info(f"Processing URL input for add_site from chat_id={user_id}")

    url = message.text.strip()

    # Validate URL
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme in ["http", "https"]:
            await message.answer(
                "Invalid URL: Scheme must be http or https. Please try again."
            )
            logger.info(
                f"Invalid URL input from chat_id={user_id}: {url} (invalid scheme)"
            )
            return
        if not parsed_url.netloc:
            await message.answer(
                "Invalid URL: Missing domain name. Please try again."
            )
            logger.info(
                f"Invalid URL input from chat_id={user_id}: {url} (missing netloc)"
            )
            return

        # Normalize URL
        normalized_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path or '/',
                '',
                '',
                '',
            )
        )

        # Load existing sites
        sites = load_sites(user_id)

        # Check for duplicates
        if any(site["url"] == normalized_url for site in sites):
            await message.answer(
                f"Site {normalized_url} is already being monitored."
            )
            logger.info(
                f"Duplicate URL input from chat_id={user_id}: {normalized_url}"
            )
            await state.clear()
            return

        # Add new site
        new_site = {
            "url": normalized_url,
            "ssl_valid": None,
            "ssl_expires": None,
            "domain_expires": None,
            "domain_last_checked": None,
            "domain_notifications": [],
            "ssl_notifications": [],
        }
        sites.append(new_site)
        save(user_id, sites)

        await message.answer(f"Site {normalized_url} added to monitoring.")
        logger.info(f"Added site {normalized_url} for chat_id={user_id}")
        await state.clear()

    except Exception as e:
        logger.error(
            f"Error processing URL input for add_site for chat_id={user_id}: {e}"
        )
        await message.answer("Error adding site. Check logs for details.")
        await state.clear()


@router.message(Command("addsite"))
async def addsite_command(message: Message):
    """Handle /addsite command to add a new website to monitoring."""
    user_id = message.chat.id
    logger.info("Received /addsite command from chat_id=%s", user_id)

    # Extract URL from command
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Please provide a URL (e.g., /addsite https://example.com)."
        )
        logger.info(
            f"Invalid /addsite command from chat_id={user_id}: No URL provided"
        )
        return

    url = args[1].strip()

    # Validate URL
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme in ["http", "https"]:
            await message.answer("Invalid URL: Scheme must be http or https.")
            logger.info(
                f"Invalid /addsite URL from chat_id={user_id}: {url} (invalid scheme)"
            )
            return
        if not parsed_url.netloc:
            await message.answer("Invalid URL: Missing domain name.")
            logger.info(
                f"Invalid /addsite URL from chat_id={user_id}: {url} (missing netloc)"
            )
            return

        # Normalize URL
        normalized_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path or '/',
                '',
                '',
                '',
            )
        )

        # Load existing sites
        sites = load_sites(user_id)

        # Check for duplicates
        if any(site["url"] == normalized_url for site in sites):
            await message.answer(
                f"Site {normalized_url} is already being monitored."
            )
            logger.info(
                f"Duplicate /addsite URL from chat_id={user_id}: {normalized_url}"
            )
            return

        # Add new site
        new_site = {
            "url": normalized_url,
            "ssl_valid": None,
            "ssl_expires": None,
            "domain_expires": None,
            "domain_last_checked": None,
            "domain_notifications": [],
            "ssl_notifications": [],
        }
        sites.append(new_site)
        save(user_id, sites)

        await message.answer(f"Site {normalized_url} added to monitoring.")
        logger.info(f"Added site {normalized_url} for chat_id={user_id}")

    except Exception as e:
        logger.error(f"Error processing /addsite for chat_id={user_id}: {e}")
        await message.answer("Error adding site. Check logs for details.")
