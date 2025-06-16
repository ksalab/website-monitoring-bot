import aiohttp
import asyncio
import certifi
import dns.resolver
import dns.exception
import logging
import ssl
import socket
import whois
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import TypedDict, Optional, List
from urllib.parse import urlparse
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
    registrar: Optional[str]
    registrar_url: Optional[str]
    error: Optional[str]
    success: bool


class DNSStatus(TypedDict):
    url: str
    a_records: List[str]
    mx_records: List[str]
    other_records: dict
    success: bool
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
    """Check domain expiration date and registrar using WHOIS.

    Args:
        domain: Domain name to check.

    Returns:
        DomainStatus: Domain expiration, registrar, and error information.
    """
    logger.debug(f"Checking domain expiration for {domain}")
    result: DomainStatus = {
        "url": domain,
        "expires": None,
        "registrar": None,
        "registrar_url": None,
        "error": None,
        "success": False,
    }

    try:
        w = whois.whois(domain)
        expiration_date = w.expiration_date
        if isinstance(expiration_date, list):
            expiration_date = expiration_date[0]

        if expiration_date:
            if isinstance(expiration_date, datetime):
                result["expires"] = expiration_date.strftime(DATE_FORMAT)
                result["success"] = True
                result["registrar"] = w.registrar
                result["registrar_url"] = w.registrar_url
                logger.info(
                    f"Domain {domain} check successful: Expires={result['expires']}, Registrar={result['registrar']}, URL={result['registrar_url']}"
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


async def check_dns_records(
    domain: str, record_types: List[str] = ["A", "MX"]
) -> DNSStatus:
    """Check DNS records for a domain, querying authoritative servers.

    Args:
        domain: Domain name to check.
        record_types: List of DNS record types to query (default: ["A", "MX"]).

    Returns:
        DNSStatus: DNS records and error information.
    """
    logger.debug(f"Checking DNS records for {domain}: types={record_types}")
    result: DNSStatus = {
        "url": domain,
        "a_records": [],
        "mx_records": [],
        "other_records": {},
        "success": False,
        "error": None,
    }

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 10  # Increased for authoritative queries

        # Get authoritative name servers
        try:
            ns_answers = await asyncio.get_event_loop().run_in_executor(
                None, lambda: resolver.resolve(domain, "NS")
            )
            name_servers = [str(rdata) for rdata in ns_answers]
            logger.debug(
                f"Authoritative name servers for {domain}: {name_servers}"
            )
            resolver.nameservers = [
                socket.gethostbyname(ns.rstrip(".")) for ns in name_servers
            ]
        except Exception as e:
            logger.warning(
                f"Failed to get NS records for {domain}: {e}, using default resolver"
            )
            resolver.nameservers = [
                "8.8.8.8",
                "8.8.4.4",
            ]  # Fallback to Google DNS

        for record_type in record_types:
            try:
                rdatatype = getattr(dns.rdatatype, record_type)
                answers = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: resolver.resolve(domain, rdatatype)
                )
                logger.debug(
                    f"Received {record_type} answers for {domain}: {answers.rrset}"
                )
                if record_type == "A":
                    result["a_records"] = sorted(
                        [str(rdata) for rdata in answers]
                    )
                elif record_type == "MX":
                    result["mx_records"] = sorted(
                        [
                            f"{rdata.preference} {rdata.exchange}"
                            for rdata in answers
                        ]
                    )
                else:
                    result["other_records"][record_type.lower()] = sorted(
                        [str(rdata) for rdata in answers]
                    )
                logger.debug(
                    f"DNS {record_type} for {domain}: {result.get(record_type.lower() + '_records', result['other_records'].get(record_type.lower()))}"
                )
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                logger.warning(f"No {record_type} records for {domain}: {e}")
                if record_type == "A":
                    result["a_records"] = []
                elif record_type == "MX":
                    result["mx_records"] = []
                else:
                    result["other_records"][record_type.lower()] = []
            except dns.exception.DNSException as e:
                logger.warning(
                    f"DNS {record_type} query failed for {domain}: {e}"
                )
                if record_type == "A":
                    result["a_records"] = []
                elif record_type == "MX":
                    result["mx_records"] = []
                else:
                    result["other_records"][record_type.lower()] = []

        result["success"] = True
        logger.info(
            f"DNS check successful for {domain}: A={result['a_records']}, MX={result['mx_records']}, Other={result['other_records']}"
        )
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"DNS check failed for {domain}: {e}")
        return result
