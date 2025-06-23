import asyncio
import logging
import re
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
from urllib.parse import urlparse, urlunparse, quote
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
    check_dns_records,
    validate_url,
)
from .config import DATE_FORMAT

logger = logging.getLogger(__name__)
router = Router()


# Define FSM for adding and removing sites
class AddSiteState(StatesGroup):
    url = State()


class RemoveSiteState(StatesGroup):
    select = State()


@router.message(CommandStart())
async def start_command(message: Message):
    """Handle /start command."""
    logger.info(f"Received /start command from chat_id={message.chat.id}")
    await message.answer(
        "Website Monitoring Bot started!\n"
        "Use /status to check current website statuses, /listsites to list monitored sites, "
        "/addsite <url> to add a new site, or /removesite <url> to remove a site."
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Handle /status command to report current status of all websites."""
    user_id = message.chat.id
    logger.info(f"Received /status command from chat_id={user_id}")
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
            parsed_url = urlparse(url)
            domain = parsed_url.hostname
            if domain:
                tasks.append(check_dns_records(domain))
            else:
                tasks.append(
                    asyncio.sleep(
                        0,
                        result={
                            "url": url,
                            "success": False,
                            "error": "Invalid domain",
                            "a_records": [],
                            "mx_records": [],
                            "other_records": {},
                        },
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, site in enumerate(sites):
            url = site["url"]
            try:
                status_result = results[i * 3]
                ssl_result = results[i * 3 + 1]
                dns_result = results[i * 3 + 2]

                parsed_url = urlparse(url)
                domain = parsed_url.hostname

                # Initialize content
                content_parts = [as_line(Text("🌐 ", url))]

                # Handle HTTP status
                if isinstance(status_result, Exception):
                    content_parts.append(
                        as_line(Text("Status: 🔴 Error during check"))
                    )
                    logger.error(
                        f"HTTP check failed for {quote(url)}: {status_result}"
                    )
                else:
                    status_emoji = (
                        "🟢" if "200" in status_result["status"] else "🔴"
                    )
                    content_parts.append(
                        as_line(
                            Text(
                                "Status: ",
                                status_emoji,
                                " ",
                                status_result["status"],
                            )
                        )
                    )
                    logger.debug(
                        f"HTTP status for {quote(url)}: {status_result['status']}"
                    )

                # Handle SSL
                if isinstance(ssl_result, Exception):
                    content_parts.append(
                        as_marked_section(
                            "--- SSL ---",
                            as_key_value("Error", "Check failed"),
                        )
                    )
                    logger.error(
                        f"SSL check failed for {quote(url)}: {ssl_result}"
                    )
                else:
                    site["ssl_valid"] = ssl_result["ssl_status"] == "valid"
                    site["ssl_expires"] = ssl_result["expires"]
                    ssl_days_left = "N/A"
                    if site["ssl_expires"]:
                        try:
                            ssl_expiry = datetime.strptime(
                                site["ssl_expires"], DATE_FORMAT
                            )
                            ssl_days_left = (ssl_expiry - datetime.now()).days
                        except ValueError:
                            logger.error(
                                f"Invalid ssl_expires format for {quote(url)}: {site['ssl_expires']}"
                            )
                    content_parts.append(
                        as_marked_section(
                            "--- SSL ---",
                            as_key_value("Valid", str(site["ssl_valid"])),
                            as_key_value(
                                "Expires", site["ssl_expires"] or "N/A"
                            ),
                            as_key_value("Days Left", str(ssl_days_left)),
                        )
                    )
                    logger.debug(
                        f"SSL status for {quote(url)}: Valid={site['ssl_valid']}, Expires={site['ssl_expires']}"
                    )

                # Handle Domain
                domain_status = "Unknown"
                domain_days_left = "N/A"
                registrar_info = Text("Unknown")
                if domain:
                    domain_result = check_domain_expiration(domain)
                    logger.debug(
                        f"WHOIS for {quote(domain)}: success={domain_result['success']}, "
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
                                    f"Invalid domain_expires format for {quote(url)}: {site['domain_expires']}"
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
                                    f"Invalid domain_expires format for {quote(url)}: {site['domain_expires']}"
                                )
                content_parts.append(
                    as_marked_section(
                        "--- Domain ---",
                        as_key_value("Expires", domain_status),
                        as_key_value("Days Left", str(domain_days_left)),
                        as_key_value("Registrar", registrar_info),
                    )
                )

                # Handle DNS
                if isinstance(dns_result, Exception) or not domain:
                    dns_status = (
                        "Error: Invalid domain"
                        if not domain
                        else f"Error: {str(dns_result)}"
                    )
                    dns_a = site.get("dns_a", []) or ["N/A"]
                    dns_mx = site.get("dns_mx", []) or ["N/A"]
                    dns_last_checked = site.get("dns_last_checked", "N/A")
                    content_parts.append(
                        as_marked_section(
                            "--- DNS ---",
                            as_key_value("DNS Status", dns_status),
                            as_key_value("A Records", ", ".join(dns_a)),
                            as_key_value("MX Records", ", ".join(dns_mx)),
                            as_key_value("Last Checked", dns_last_checked),
                        )
                    )
                    logger.error(
                        f"DNS check failed for {quote(url)}: {dns_result}"
                    )
                else:
                    if dns_result["success"]:
                        site["dns_a"] = dns_result.get("a_records", [])
                        site["dns_mx"] = dns_result.get("mx_records", [])
                        site["dns_last_checked"] = datetime.now().strftime(
                            DATE_FORMAT
                        )
                        site["dns_records"] = dns_result.get(
                            "other_records", {}
                        )
                        dns_status = "OK"
                    else:
                        dns_status = f"Error: {dns_result['error']}"
                    dns_a = site["dns_a"] or ["N/A"]
                    dns_mx = site["dns_mx"] or ["N/A"]
                    content_parts.append(
                        as_marked_section(
                            "--- DNS ---",
                            as_key_value("DNS Status", dns_status),
                            as_key_value("A Records", ", ".join(dns_a)),
                            as_key_value("MX Records", ", ".join(dns_mx)),
                        )
                    )
                    logger.info(
                        f"DNS processed for {quote(url)}: A={dns_a}, MX={dns_mx}, Status={dns_status}"
                    )

                # Build and send response
                content = as_list(*content_parts)
                try:
                    text, entities = content.render()
                    logger.debug(
                        f"Sending /status message for {quote(url)}: text={text}, entities={entities}"
                    )
                    await message.answer(**content.as_kwargs())
                    logger.info(
                        f"Sent /status response for {quote(url)} to chat_id={user_id}"
                    )
                except TelegramBadRequest as e:
                    logger.error(
                        f"Failed to send /status message for {quote(url)} to chat_id={user_id}: {e}"
                    )
                    await message.answer(
                        f"Error sending status for {quote(url)}. Check logs for details."
                    )

            except Exception as e:
                logger.error(
                    f"Error processing status for {quote(url)} for user_id={user_id}: {e}"
                )
                await message.answer(
                    f"Error processing status for {quote(url)}. Check logs for details."
                )

        save(user_id, sites)
        logger.debug(f"Saved updated sites for user_id={user_id}")
    except Exception as e:
        logger.error(f"/status command failed for user_id={user_id}: {e}")
        await message.answer(
            "Error retrieving statuses. Check logs for details."
        )


@router.message(Command("listsites"))
async def listsites_command(message: Message):
    """Handle /listsites command to list all monitored websites."""
    user_id = message.chat.id
    logger.info(f"Received /listsites command from chat_id={user_id}")
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

        # Add inline buttons
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Add site", callback_data="add_site"
                    ),
                    InlineKeyboardButton(
                        text="Remove site", callback_data="remove_site"
                    ),
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
    user_id = callback_query.from_user.id
    logger.info(f"Received add_site callback from user_id={user_id}")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Cancel", callback_data="cancel_add_site"
                )
            ]
        ]
    )
    await callback_query.message.answer(
        "Please enter the URL of the new site (e.g., https://example.com).",
        reply_markup=keyboard,
    )
    await state.set_state(AddSiteState.url)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "cancel_add_site")
async def cancel_add_site_callback(
    callback_query: CallbackQuery, state: FSMContext
):
    """Handle 'Cancel' button callback for adding a site."""
    user_id = callback_query.from_user.id
    logger.info(f"Received cancel_add_site callback from user_id={user_id}")
    await state.clear()
    await callback_query.message.answer(
        "Adding a new site has been cancelled."
    )
    await callback_query.answer()


@router.message(
    AddSiteState.url,
    Command(
        commands=["start", "status", "listsites", "addsite", "removesite"]
    ),
)
async def handle_commands_in_add_state(message: Message, state: FSMContext):
    """Handle commands during AddSiteState.url to reset state."""
    logger.info(
        f"Received command {message.text} in AddSiteState.url from chat_id={message.chat.id}"
    )
    await state.clear()
    await message.answer(
        "Adding a new site has been cancelled due to new command."
    )
    # Re-dispatch the command
    await router.propagate_event("message", message)


@router.message(AddSiteState.url, F.text)
async def process_add_site_url(message: Message, state: FSMContext):
    """Process URL input for adding a new site."""
    user_id = message.chat.id
    url = message.text.strip()
    logger.info(
        f"Processing URL input for add_site from chat_id={user_id}: {quote(url)}"
    )

    # Validate URL
    validation_result = validate_url(url)
    if not validation_result["valid"]:
        await message.answer(validation_result["error"])
        logger.info(
            f"Invalid URL input from chat_id={user_id}: {quote(url)} ({validation_result['error']})"
        )
        return

    normalized_url = validation_result["normalized_url"]

    # Load existing sites
    sites = load_sites(user_id)

    # Check for duplicates
    if any(site["url"] == normalized_url for site in sites):
        await message.answer(
            f"Site {normalized_url} is already being monitored."
        )
        logger.info(
            f"Duplicate URL input from chat_id={user_id}: {quote(normalized_url)}"
        )
        await state.clear()
        return

    # Add new site
    new_site: SiteConfig = {
        "url": normalized_url,
        "ssl_valid": None,
        "ssl_expires": None,
        "domain_expires": None,
        "domain_last_checked": None,
        "domain_notifications": [],
        "ssl_notifications": [],
        "dns_a": None,
        "dns_mx": None,
        "dns_last_checked": None,
        "dns_records": {},
    }
    sites.append(new_site)
    save(user_id, sites)

    await message.answer(f"Site {normalized_url} added to monitoring.")
    logger.info(f"Added site {quote(normalized_url)} for chat_id={user_id}")
    await state.clear()


@router.message(Command("addsite"))
async def addsite_command(message: Message):
    """Handle /addsite command to add a new website to monitoring."""
    user_id = message.chat.id
    logger.info(f"Received /addsite command from chat_id={user_id}")

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
    validation_result = validate_url(url)
    if not validation_result["valid"]:
        await message.answer(validation_result["error"])
        logger.info(
            f"Invalid /addsite URL from chat_id={user_id}: {quote(url)} ({validation_result['error']})"
        )
        return

    normalized_url = validation_result["normalized_url"]

    # Load existing sites
    sites = load_sites(user_id)

    # Check for duplicates
    if any(site["url"] == normalized_url for site in sites):
        await message.answer(
            f"Site {normalized_url} is already being monitored."
        )
        logger.info(
            f"Duplicate /addsite URL from chat_id={user_id}: {quote(normalized_url)}"
        )
        return

    # Add new site
    new_site: SiteConfig = {
        "url": normalized_url,
        "ssl_valid": None,
        "ssl_expires": None,
        "domain_expires": None,
        "domain_last_checked": None,
        "domain_notifications": [],
        "ssl_notifications": [],
        "dns_a": None,
        "dns_mx": None,
        "dns_last_checked": None,
        "dns_records": {},
    }
    sites.append(new_site)
    save(user_id, sites)

    await message.answer(f"Site {normalized_url} added to monitoring.")
    logger.info(f"Added site {quote(normalized_url)} for chat_id={user_id}")


@router.message(Command("removesite"))
async def removesite_command(message: Message):
    """Handle /removesite command to remove a website from monitoring."""
    user_id = message.chat.id
    logger.info(f"Received /removesite command from chat_id={user_id}")

    # Extract URL from command
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Please provide a URL (e.g., /removesite https://example.com)."
        )
        logger.info(
            f"Invalid /removesite command from chat_id={user_id}: No URL provided"
        )
        return

    url = args[1].strip()

    # Validate URL
    validation_result = validate_url(url)
    if not validation_result["valid"]:
        await message.answer(validation_result["error"])
        logger.info(
            f"Invalid /removesite URL from chat_id={user_id}: {quote(url)} ({validation_result['error']})"
        )
        return

    normalized_url = validation_result["normalized_url"]

    # Load existing sites
    sites = load_sites(user_id)

    # Check if site exists
    site_to_remove = next(
        (site for site in sites if site["url"] == normalized_url), None
    )
    if not site_to_remove:
        await message.answer(f"Site {normalized_url} is not being monitored.")
        logger.info(
            f"Site not found for /removesite from chat_id={user_id}: {quote(normalized_url)}"
        )
        return

    # Remove site
    sites.remove(site_to_remove)
    save(user_id, sites)

    await message.answer(f"Site {normalized_url} removed from monitoring.")
    logger.info(f"Removed site {quote(normalized_url)} for chat_id={user_id}")


@router.callback_query(lambda c: c.data == "remove_site")
async def remove_site_callback(
    callback_query: CallbackQuery, state: FSMContext
):
    """Handle 'Remove site' button callback."""
    user_id = callback_query.from_user.id
    logger.info(f"Received remove_site callback from user_id={user_id}")

    try:
        sites = load_sites(user_id)
        if not sites:
            await callback_query.message.edit_text(
                "No sites are currently monitored. Use /addsite <url> to add a new site."
            )
            logger.info(
                f"Sent empty remove_site response to user_id={user_id}"
            )
            await state.clear()
            await callback_query.answer()
            return

        # Build inline keyboard with domain names and Cancel
        domain_counts = {}
        keyboard_buttons = []
        for site in sites:
            parsed_url = urlparse(site["url"])
            domain = parsed_url.hostname or "unknown"
            # Handle duplicate domains
            if domain in domain_counts:
                domain_counts[domain] += 1
                button_text = f"{domain} ({domain_counts[domain]})"
            else:
                domain_counts[domain] = 0
                button_text = domain
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        text=button_text, callback_data=f"remove:{site['url']}"
                    )
                ]
            )
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="Cancel", callback_data="cancel_remove_site"
                )
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Update message with site selection
        await callback_query.message.edit_text(
            "Select a site to remove:", reply_markup=keyboard
        )
        await state.set_state(RemoveSiteState.select)
        await callback_query.answer()

    except TelegramBadRequest as e:
        logger.error(
            f"Failed to edit message for remove_site for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error updating site list. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()
    except Exception as e:
        logger.error(
            f"Error processing remove_site callback for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error removing site. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("remove:"))
async def remove_selected_site_callback(
    callback_query: CallbackQuery, state: FSMContext
):
    """Handle site removal from selection."""
    user_id = callback_query.from_user.id
    url = callback_query.data[len("remove:") :]
    logger.info(
        f"Received remove_selected_site callback for url={quote(url)} from user_id={user_id}"
    )

    try:
        # Validate URL
        validation_result = validate_url(url)
        if not validation_result["valid"]:
            await callback_query.message.edit_text(validation_result["error"])
            logger.info(
                f"Invalid URL in remove_selected_site from user_id={user_id}: {quote(url)} ({validation_result['error']})"
            )
            await state.clear()
            await callback_query.answer()
            return

        normalized_url = validation_result["normalized_url"]

        # Load existing sites
        sites = load_sites(user_id)

        # Check if site exists
        site_to_remove = next(
            (site for site in sites if site["url"] == normalized_url), None
        )
        if not site_to_remove:
            await callback_query.message.edit_text(
                f"Site {normalized_url} is not being monitored."
            )
            logger.info(
                f"Site not found for remove_selected_site from user_id={user_id}: {quote(normalized_url)}"
            )
            await state.clear()
            await callback_query.answer()
            return

        # Remove site
        sites.remove(site_to_remove)
        save(user_id, sites)

        # Refresh the /listsites view
        if sites:
            content = Text("Monitored websites:\n\n")
            for site in sites:
                content += Text("- ", site["url"], "\n")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Add site", callback_data="add_site"
                        ),
                        InlineKeyboardButton(
                            text="Remove site", callback_data="remove_site"
                        ),
                    ]
                ]
            )
            await callback_query.message.edit_text(
                **content.as_kwargs(), reply_markup=keyboard
            )
        else:
            await callback_query.message.edit_text(
                "No sites are currently monitored. Use /addsite <url> to add a new site."
            )

        await callback_query.message.answer(
            f"Site {normalized_url} removed from monitoring."
        )
        logger.info(
            f"Removed site {quote(normalized_url)} for user_id={user_id}"
        )
        await state.clear()
        await callback_query.answer()

    except TelegramBadRequest as e:
        logger.error(
            f"Failed to edit message for remove_selected_site for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error updating site list. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()
    except Exception as e:
        logger.error(
            f"Error processing remove_selected_site for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error removing site. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()


@router.callback_query(lambda c: c.data == "cancel_remove_site")
async def cancel_remove_site_callback(
    callback_query: CallbackQuery, state: FSMContext
):
    """Handle 'Cancel' button callback for removing a site."""
    user_id = callback_query.from_user.id
    logger.info(f"Received cancel_remove_site callback from user_id={user_id}")

    try:
        # Refresh the /listsites view
        sites = load_sites(user_id)
        if sites:
            content = Text("Monitored websites:\n\n")
            for site in sites:
                content += Text("- ", site["url"], "\n")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Add site", callback_data="add_site"
                        ),
                        InlineKeyboardButton(
                            text="Remove site", callback_data="remove_site"
                        ),
                    ]
                ]
            )
            await callback_query.message.edit_text(
                **content.as_kwargs(), reply_markup=keyboard
            )
        else:
            await callback_query.message.edit_text(
                "No sites are currently monitored. Use /addsite <url> to add a new site."
            )

        await callback_query.message.answer(
            "Removing a site has been cancelled."
        )
        logger.info(f"Cancelled site removal for user_id={user_id}")
        await state.clear()
        await callback_query.answer()

    except TelegramBadRequest as e:
        logger.error(
            f"Failed to edit message for cancel_remove_site for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error updating site list. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()
    except Exception as e:
        logger.error(
            f"Error processing cancel_remove_site for user_id={user_id}: {e}"
        )
        await callback_query.message.answer(
            "Error cancelling site removal. Check logs for details."
        )
        await state.clear()
        await callback_query.answer()


@router.message(
    RemoveSiteState.select,
    Command(
        commands=["start", "status", "listsites", "addsite", "removesite"]
    ),
)
async def handle_commands_in_remove_state(message: Message, state: FSMContext):
    """Handle commands during RemoveSiteState.select to reset state."""
    logger.info(
        f"Received command {message.text} in RemoveSiteState.select from chat_id={message.chat.id}"
    )
    await state.clear()
    await message.answer(
        "Removing a site has been cancelled due to new command."
    )
    # Re-dispatch the command
    await router.propagate_event("message", message)
