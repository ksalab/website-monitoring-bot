import json
import logging
import os
from typing import List, TypedDict
from .config import DATA_DIR

logger = logging.getLogger(__name__)


class SiteConfig(TypedDict):
    url: str
    ssl_valid: bool | None
    ssl_expires: str | None
    domain_expires: str | None
    domain_last_checked: str | None
    domain_notifications: List[int]
    ssl_notifications: List[int]


def get_user_sites_path(user_id: int) -> str:
    """Get path to user's sites file.

    Args:
        user_id: Telegram user or chat ID.

    Returns:
        str: Path to data/<user_id>.json.
    """
    return os.path.join(DATA_DIR, f"{user_id}.json")


def load_sites(user_id: int) -> List[SiteConfig]:
    """Load list of websites for a specific user.

    Args:
        user_id: Telegram user or chat ID.

    Returns:
        List[SiteConfig]: List of site configurations.

    Raises:
        ValueError: If JSON is invalid or site entries are malformed.
    """
    sites_path = get_user_sites_path(user_id)
    logger.debug(
        f"Attempting to load sites for user_id={user_id} from: {sites_path}"
    )
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(sites_path):
        logger.info(
            f"No sites file found for user_id={user_id}, returning empty list"
        )
        return []

    try:
        with open(sites_path, "r") as file:
            sites = json.load(file)
            for site in sites:
                if not isinstance(site, dict) or "url" not in site:
                    logger.error(f"Invalid site entry in {sites_path}: {site}")
                    raise ValueError(f"Invalid site entry: {site}")
                site.setdefault("domain_notifications", [])
                site.setdefault("ssl_notifications", [])
            logger.info(
                f"Successfully loaded {len(sites)} sites for user_id={user_id} from {sites_path}"
            )
            return sites
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to load sites for user_id={user_id}: Invalid JSON in {sites_path}: {e}"
        )
        raise ValueError(f"Invalid JSON in {sites_path}: {e}")


def save(user_id: int, sites: List[SiteConfig]) -> None:
    """Save updated sites for a specific user.

    Args:
        user_id: Telegram user or chat ID.
        sites: List of site configurations to save.

    Raises:
        OSError: If file writing fails.
    """
    sites_path = get_user_sites_path(user_id)
    logger.debug(
        f"Attempting to save {len(sites)} sites for user_id={user_id} to: {sites_path}"
    )
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        with open(sites_path, "w") as file:
            json.dump(sites, file, indent=2)
        logger.info(
            f"Successfully saved {len(sites)} sites for user_id={user_id} to {sites_path}"
        )
    except OSError as e:
        logger.error(
            f"Failed to save sites for user_id={user_id} to {sites_path}: {e}"
        )
        raise
