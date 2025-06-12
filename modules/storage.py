import json
import logging
from typing import List, TypedDict
from .config import SITES_PATH

logger = logging.getLogger(__name__)


class SiteConfig(TypedDict):
    url: str
    ssl_valid: bool | None
    ssl_expires: str | None
    domain_expires: str | None
    domain_last_checked: str | None
    domain_notifications: List[int]
    ssl_notifications: List[int]


def load_sites() -> List[SiteConfig]:
    """Load list of websites from sites.json.

    Returns:
        List[SiteConfig]: List of site configurations.

    Raises:
        FileNotFoundError: If sites.json is not found.
        ValueError: If JSON is invalid or site entries are malformed.
    """
    logger.debug(f"Attempting to load sites from: {SITES_PATH}")
    try:
        with open(SITES_PATH, "r") as file:
            sites = json.load(file)
            for site in sites:
                if not isinstance(site, dict) or "url" not in site:
                    logger.error(f"Invalid site entry in {SITES_PATH}: {site}")
                    raise ValueError(f"Invalid site entry: {site}")
                site.setdefault("domain_notifications", [])
                site.setdefault("ssl_notifications", [])
            logger.info(
                f"Successfully loaded {len(sites)} sites from {SITES_PATH}"
            )
            return sites
    except FileNotFoundError as e:
        logger.error(f"Failed to load sites: {SITES_PATH} not found")
        raise
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to load sites: Invalid JSON in {SITES_PATH}: {e}"
        )
        raise


def save(sites: List[SiteConfig]) -> None:
    """Save updated sites to sites.json.

    Args:
        sites: List of site configurations to save.

    Raises:
        OSError: If file writing fails.
    """
    logger.debug(f"Attempting to save {len(sites)} sites to: {SITES_PATH}")
    try:
        with open(SITES_PATH, "w") as file:
            json.dump(sites, file, indent=2)
        logger.info(f"Successfully saved {len(sites)} sites to {SITES_PATH}")
    except Exception as e:
        logger.error(f"Failed to save sites to {SITES_PATH}: {e}")
        raise
