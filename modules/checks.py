import ssl
import socket
import aiohttp
import logging
from datetime import datetime
from typing import TypedDict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import urlparse
import whois
import certifi
from .config import DATE_FORMAT, CERT_DATE_FORMAT

logger = logging.getLogger(__name__)


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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def check_website_status(url: str) -> WebsiteStatus:
    """Check website HTTP status with retries.

    Args:
        url: Website URL to check.

    Returns:
        WebsiteStatus: Status and error information.
    """
    logger.debug(f"Checking website status for {url}")
    result: WebsiteStatus = {"url": url, "status": "unknown", "error": None}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                result["status"] = f"{response.status} {response.reason}"
                logger.info(
                    f"Website {url} check successful: Status={result['status']}"
                )
                return result
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "down"
        logger.warning(f"Website check failed for {url}: {e}")
        return result


def check_ssl_certificate_manual(hostname: str, port: int = 443) -> SSLStatus:
    """Check SSL certificate using ssl.SSLSocket.

    Args:
        hostname: Hostname to check.
        port: Port number (default: 443).

    Returns:
        SSLStatus: SSL status and expiration information.
    """
    logger.debug(f"Checking SSL certificate for {hostname}:{port}")
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
                logger.debug(f"SSL certificate for {hostname}: {cert}")
                if cert:
                    expires = datetime.strptime(
                        cert["notAfter"], CERT_DATE_FORMAT
                    )
                    result["ssl_status"] = "valid"
                    result["expires"] = expires.strftime(DATE_FORMAT)
                    logger.info(
                        f"SSL check successful for {hostname}: Valid, expires={result['expires']}"
                    )
                else:
                    result["ssl_status"] = "no_ssl"
                    result["error"] = "No certificate provided"
                    logger.warning(
                        f"SSL check failed for {hostname}: No certificate provided"
                    )
    except Exception as e:
        result["error"] = str(e)
        result["ssl_status"] = "invalid"
        logger.warning(f"SSL check failed for {hostname}: {e}")
    return result


async def check_ssl_certificate(url: str) -> SSLStatus:
    """Check SSL certificate for a website.

    Args:
        url: Website URL to check.

    Returns:
        SSLStatus: SSL status and expiration information.
    """
    logger.debug(f"Checking SSL certificate for URL: {url}")
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    port = parsed_url.port or 443

    if not hostname:
        logger.error(f"Invalid URL for SSL check: {url}")
        return {
            "url": url,
            "ssl_status": "invalid",
            "expires": None,
            "error": "Invalid URL",
        }

    return check_ssl_certificate_manual(hostname, port)


def check_domain_expiration(domain: str) -> DomainStatus:
    """Check domain expiration date using WHOIS.

    Args:
        domain: Domain name to check.

    Returns:
        DomainStatus: Domain expiration information.
    """
    logger.debug(f"Checking domain expiration for {domain}")
    result: DomainStatus = {
        "url": domain,
        "expires": None,
        "error": None,
    }

    try:
        w = whois.whois(domain)
        expiration_date = w.expiration_date
        if isinstance(expiration_date, list):
            expiration_date = expiration_date[0]

        if expiration_date:
            if isinstance(expiration_date, datetime):
                result["expires"] = expiration_date.strftime(DATE_FORMAT)
                logger.info(
                    f"Domain {domain} check successful: Expires={result['expires']}"
                )
            else:
                result["error"] = "Invalid expiration date format"
                logger.warning(
                    f"Domain check failed for {domain}: Invalid expiration date format"
                )
        else:
            result["error"] = "No expiration date found"
            logger.warning(
                f"Domain check failed for {domain}: No expiration date found"
            )
    except Exception as e:
        result["error"] = str(e)
        logger.warning(f"Domain check failed for {domain}: {e}")
    return result
