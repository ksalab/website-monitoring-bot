import os
from typing import Dict, List
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Constants
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def load_config() -> Dict[str, any]:
    """Load and validate configuration from .env file.

    Returns:
        Dict[str, any]: Validated configuration dictionary.

    Raises:
        ValueError: If required parameters are missing or invalid.
    """
    logger.debug(f"Loading .env from: {ENV_PATH}")
    load_dotenv(ENV_PATH, override=True)

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

    # Validation
    if not config["BOT_TOKEN"]:
        logger.error("Configuration error: BOT_TOKEN is required")
        raise ValueError("BOT_TOKEN is required")

    if config["NOTIFICATION_MODE"] not in ["group", "user"]:
        logger.error(
            f"Configuration error: NOTIFICATION_MODE must be 'group' or 'user', got: {config['NOTIFICATION_MODE']}"
        )
        raise ValueError(
            f"NOTIFICATION_MODE must be 'group' or 'user', got: {config['NOTIFICATION_MODE']!r}"
        )

    if config["NOTIFICATION_MODE"] == "group" and not config["GROUP_ID"]:
        logger.error(
            "Configuration error: GROUP_ID is required when NOTIFICATION_MODE is 'group'"
        )
        raise ValueError(
            "GROUP_ID is required when NOTIFICATION_MODE is 'group'"
        )

    if config["NOTIFICATION_MODE"] == "user" and not config["USER_ID"]:
        logger.error(
            "Configuration error: USER_ID is required when NOTIFICATION_MODE is 'user'"
        )
        raise ValueError(
            "USER_ID is required when NOTIFICATION_MODE is 'user'"
        )

    try:
        config["CHECK_INTERVAL"] = int(config["CHECK_INTERVAL"])
        logger.debug(
            f"Parsed CHECK_INTERVAL: {config['CHECK_INTERVAL']} seconds"
        )
    except ValueError:
        logger.error(
            f"Configuration error: CHECK_INTERVAL must be a valid integer, got: {config['CHECK_INTERVAL']}"
        )
        raise ValueError(
            f"CHECK_INTERVAL must be a valid integer, got: {config['CHECK_INTERVAL']!r}"
        )

    try:
        config["DOMAIN_EXPIRY_THRESHOLD"] = [
            int(x) for x in config["DOMAIN_EXPIRY_THRESHOLD"].split(",")
        ]
        logger.debug(
            f"Parsed DOMAIN_EXPIRY_THRESHOLD: {config['DOMAIN_EXPIRY_THRESHOLD']}"
        )
    except ValueError:
        logger.error(
            f"Configuration error: DOMAIN_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['DOMAIN_EXPIRY_THRESHOLD']}"
        )
        raise ValueError(
            f"DOMAIN_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['DOMAIN_EXPIRY_THRESHOLD']!r}"
        )

    try:
        config["SSL_EXPIRY_THRESHOLD"] = [
            int(x) for x in config["SSL_EXPIRY_THRESHOLD"].split(",")
        ]
        logger.debug(
            f"Parsed SSL_EXPIRY_THRESHOLD: {config['SSL_EXPIRY_THRESHOLD']}"
        )
    except ValueError:
        logger.error(
            f"Configuration error: SSL_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['SSL_EXPIRY_THRESHOLD']}"
        )
        raise ValueError(
            f"SSL_EXPIRY_THRESHOLD must be comma-separated integers, got: {config['SSL_EXPIRY_THRESHOLD']!r}"
        )

    if config["TOPIC_ID"]:
        try:
            config["TOPIC_ID"] = config["TOPIC_ID"].split("#")[0].strip()
            int(config["TOPIC_ID"])
            logger.debug(f"Parsed TOPIC_ID: {config['TOPIC_ID']}")
        except ValueError:
            logger.error(
                f"Configuration error: TOPIC_ID must be a valid integer, got: {config['TOPIC_ID']}"
            )
            raise ValueError(
                f"TOPIC_ID must be a valid integer, got: {config['TOPIC_ID']!r}"
            )

    if config["USER_ID"]:
        try:
            int(config["USER_ID"])
            logger.debug(f"Parsed USER_ID: {config['USER_ID']}")
        except ValueError:
            logger.error(
                f"Configuration error: USER_ID must be a valid integer, got: {config['USER_ID']}"
            )
            raise ValueError(
                f"USER_ID must be a valid integer, got: {config['USER_ID']!r}"
            )

    logger.info("Configuration loaded successfully")
    return config
