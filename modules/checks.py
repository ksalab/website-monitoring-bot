import aiohttp
import asyncio
import certifi
import dns.resolver
import dns.exception
import logging
import ssl
import socket
import whois
import ipaddress
import re
import idna
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import TypedDict, Optional, List
from urllib.parse import urlparse, urlunparse, quote
from .config import DATE_FORMAT, CERT_DATE_FORMAT

logger = logging.getLogger(__name__)

# Maximum URL length
MAX_URL_LENGTH = 300

# Regular expression for validating domain names (basic ASCII validation)
DOMAIN_REGEX = re.compile(r'^[a-zA-Z0-9.-]+$')


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


class URLValidationResult(TypedDict):
    valid: bool
    error: Optional[str]
    normalized_url: Optional[str]


def validate_url(url: str) -> URLValidationResult:
    """Validate and normalize a URL, ensuring it contains only a domain.

    Args:
        url: URL to validate.

    Returns:
        URLValidationResult: Validation status, error message, and normalized URL.
    """
    logger.debug(f"Validating URL: {quote(url)}")
    result: URLValidationResult = {
        "valid": False,
        "error": None,
        "normalized_url": None,
    }

    # Check URL length
    if len(url) > MAX_URL_LENGTH:
        result["error"] = f"URL is too long (max {MAX_URL_LENGTH} characters)."
        logger.warning(f"URL validation failed: {quote(url)} (too long)")
        return result

    # Check for control characters
    if any(c in url for c in '\n\r\t'):
        result["error"] = "URL contains invalid control characters."
        logger.warning(
            f"URL validation failed: {quote(url)} (control characters)"
        )
        return result

    # Parse URL
    try:
        parsed_url = urlparse(url)
    except ValueError as e:
        result["error"] = "Invalid URL format."
        logger.warning(
            f"URL validation failed: {quote(url)} (invalid format: {e})"
        )
        return result

    # Check scheme
    if parsed_url.scheme not in ["http", "https"]:
        result["error"] = "URL scheme must be http or https."
        logger.warning(f"URL validation failed: {quote(url)} (invalid scheme)")
        return result

    # Check netloc (domain)
    if not parsed_url.netloc:
        result["error"] = "URL must contain a domain name."
        logger.warning(f"URL validation failed: {quote(url)} (missing netloc)")
        return result

    # Check for path, query, or fragment
    if (
        parsed_url.path not in ["", "/"]
        or parsed_url.query
        or parsed_url.fragment
    ):
        result["error"] = (
            "URL must contain only a domain (no path, query, or fragment)."
        )
        logger.warning(
            f"URL validation failed: {quote(url)} (contains path/query/fragment)"
        )
        return result

    # Check for port
    if parsed_url.port:
        result["error"] = "URL must not contain a port."
        logger.warning(f"URL validation failed: {quote(url)} (contains port)")
        return result

    # Validate domain format
    domain = parsed_url.netloc
    try:
        # Handle Punycode
        decoded_domain = idna.decode(domain)
        if not DOMAIN_REGEX.match(decoded_domain):
            result["error"] = "Domain contains invalid characters."
            logger.warning(
                f"URL validation failed: {quote(url)} (invalid domain characters)"
            )
            return result
    except idna.IDNAError as e:
        result["error"] = "Invalid domain name (Punycode error)."
        logger.warning(
            f"URL validation failed: {quote(url)} (Punycode error: {e})"
        )
        return result

    # Check for local/private addresses
    is_local, error = is_local_or_private_address(domain)
    if is_local:
        result["error"] = error
        logger.warning(
            f"URL validation failed: {quote(url)} (local/private address)"
        )
        return result

    # Check for common local hostnames
    if domain.lower() in ["localhost", "127.0.0.1", "::1"]:
        result["error"] = "Local or private addresses are not allowed."
        logger.warning(f"URL validation failed: {quote(url)} (local hostname)")
        return result

    # Check for injection characters in domain
    if any(c in domain for c in '<>;'):
        result["error"] = "Domain contains invalid characters (<, >, ;)."
        logger.warning(
            f"URL validation failed: {quote(url)} (injection characters)"
        )
        return result

    # Normalize URL
    normalized_url = urlunparse(
        (parsed_url.scheme, parsed_url.netloc, "", "", "", "")
    )
    result["valid"] = True
    result["normalized_url"] = normalized_url
    logger.info(
        f"URL validation successful: {quote(url)} -> {quote(normalized_url)}"
    )
    return result


def is_local_or_private_address(hostname: str) -> tuple[bool, str]:
    """Check if hostname is a local or private address.

    Args:
        hostname: Hostname or IP address to check.

    Returns:
        tuple[bool, str]: (Is local/private, Error message if applicable).
    """
    logger.debug(f"Checking if {quote(hostname)} is local/private")

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback:
            return True, "Local or private addresses are not allowed."
    except ValueError:
        # Not an IP address, proceed
        pass

    if hostname.lower() in ["localhost", "127.0.0.1", "::1"]:
        return True, "Local or private addresses are not allowed."

    return False, ""


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
    logger.debug(f"Checking website status for {quote(url)}")
    result: WebsiteStatus = {"url": url, "status": "unknown", "error": None}

    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    # Check for local/private addresses
    is_local, error = is_local_or_private_address(domain)
    if is_local:
        result["error"] = error
        result["status"] = "down"
        logger.warning(f"Website check failed for {quote(url)}: {error}")
        return result

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                result["status"] = f"{response.status} {response.reason}"
                logger.info(
                    f"Website {quote(url)} check successful: Status={result['status']}"
                )
                return result
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "down"
        logger.warning(f"Website check failed for {quote(url)}: {e}")
        return result


def check_ssl_certificate_manual(hostname: str, port: int = 443) -> SSLStatus:
    """Check SSL certificate using ssl.SSLSocket.

    Args:
        hostname: Hostname to check.
        port: Port number (default: 443).

    Returns:
        SSLStatus: SSL status and expiration information.
    """
    logger.debug(f"Checking SSL certificate for {quote(hostname)}:{port}")
    result: SSLStatus = {
        "url": f"https://{hostname}",
        "ssl_status": "unknown",
        "expires": None,
        "error": None,
    }

    # Check for local/private addresses
    is_local, error = is_local_or_private_address(hostname)
    if is_local:
        result["error"] = error
        result["ssl_status"] = "invalid"
        logger.warning(f"SSL check failed for {quote(hostname)}: {error}")
        return result

    try:
        context = ssl.create_default_context(cafile=certifi.where())
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                logger.debug(f"SSL certificate for {quote(hostname)}: {cert}")
                if cert:
                    expires = datetime.strptime(
                        cert["notAfter"], CERT_DATE_FORMAT
                    )
                    result["ssl_status"] = "valid"
                    result["expires"] = expires.strftime(DATE_FORMAT)
                    logger.info(
                        f"SSL check successful for {quote(hostname)}: Valid, expires={result['expires']}"
                    )
                else:
                    result["ssl_status"] = "no_ssl"
                    result["error"] = "No certificate provided"
                    logger.warning(
                        f"SSL check failed for {quote(hostname)}: No certificate provided"
                    )
    except Exception as e:
        result["error"] = str(e)
        result["ssl_status"] = "invalid"
        logger.warning(f"SSL check failed for {quote(hostname)}: {e}")
    return result


async def check_ssl_certificate(url: str) -> SSLStatus:
    """Check SSL certificate for a website.

    Args:
        url: Website URL to check.

    Returns:
        SSLStatus: SSL status and expiration information.
    """
    logger.debug(f"Checking SSL certificate for URL: {quote(url)}")
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    port = parsed_url.port or 443

    if not hostname:
        logger.error(f"Invalid URL for SSL check: {quote(url)}")
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
    logger.debug(f"Checking domain expiration for {quote(domain)}")
    result: DomainStatus = {
        "url": domain,
        "expires": None,
        "registrar": None,
        "registrar_url": None,
        "error": None,
        "success": False,
    }

    # Check for local/private addresses
    is_local, error = is_local_or_private_address(domain)
    if is_local:
        result["error"] = error
        logger.warning(f"Domain check failed for {quote(domain)}: {error}")
        return result

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
                    f"Domain {quote(domain)} check successful: Expires={result['expires']}, Registrar={result['registrar']}, URL={result['registrar_url']}"
                )
            else:
                result["error"] = "Invalid expiration date format"
                logger.warning(
                    f"Domain check failed for {quote(domain)}: Invalid expiration date format"
                )
        else:
            result["error"] = "No expiration date found"
            logger.warning(
                f"Domain check failed for {quote(domain)}: No expiration date found"
            )
    except Exception as e:
        result["error"] = str(e)
        logger.warning(f"Domain check failed for {quote(domain)}: {e}")
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
    logger.debug(
        f"Checking DNS records for {quote(domain)}: types={record_types}"
    )
    result: DNSStatus = {
        "url": domain,
        "a_records": [],
        "mx_records": [],
        "other_records": {},
        "success": False,
        "error": None,
    }

    # Check for local/private addresses
    is_local, error = is_local_or_private_address(domain)
    if is_local:
        result["error"] = error
        logger.warning(f"DNS check failed for {quote(domain)}: {error}")
        return result

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
                f"Authoritative name servers for {quote(domain)}: {name_servers}"
            )
            resolver.nameservers = [
                socket.gethostbyname(ns.rstrip(".")) for ns in name_servers
            ]
        except Exception as e:
            logger.warning(
                f"Failed to get NS records for {quote(domain)}: {e}, using default resolver"
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
                    f"Received {record_type} answers for {quote(domain)}: {answers.rrset}"
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
                    f"DNS {record_type} for {quote(domain)}: {result.get(record_type.lower() + '_records', result['other_records'].get(record_type.lower()))}"
                )
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                logger.warning(
                    f"No {record_type} records for {quote(domain)}: {e}"
                )
                if record_type == "A":
                    result["a_records"] = []
                elif record_type == "MX":
                    result["mx_records"] = []
                else:
                    result["other_records"][record_type.lower()] = []
            except dns.exception.DNSException as e:
                logger.warning(
                    f"DNS {record_type} query failed for {quote(domain)}: {e}"
                )
                if record_type == "A":
                    result["a_records"] = []
                elif record_type == "MX":
                    result["mx_records"] = []
                else:
                    result["other_records"][record_type.lower()] = []

        result["success"] = True
        logger.info(
            f"DNS check successful for {quote(domain)}: A={result['a_records']}, MX={result['mx_records']}, Other={result['other_records']}"
        )
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"DNS check failed for {quote(domain)}: {e}")
        return result
