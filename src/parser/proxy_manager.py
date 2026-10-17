"""Proxy parsing, conversion for Playwright/HTTPX, and connectivity checker."""

import time
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import quote, unquote, urlparse

import httpx

from src.db.models import Proxy

SUPPORTED_PROTOCOLS = {"http", "https", "socks5"}


def parse_proxy_string(raw_proxy: str) -> Dict[str, Any]:
    """Parse proxy string in various formats into structured dictionary.

    Supported formats:
    1. host:port (defaults to http)
    2. host:port:username:password (defaults to http)
    3. protocol://host:port (http, https, socks5)
    4. protocol://username:password@host:port

    Args:
        raw_proxy: Raw proxy string.

    Returns:
        Dictionary with keys: raw_proxy, protocol, host, port, username, password.

    Raises:
        ValueError: If proxy string format is invalid.
    """
    if not raw_proxy or not raw_proxy.strip():
        raise ValueError("Proxy string cannot be empty.")

    cleaned = raw_proxy.strip()

    if "://" in cleaned:
        parsed = urlparse(cleaned)
        protocol = (parsed.scheme or "").lower()
        if protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported proxy protocol '{protocol}'. Allowed: {', '.join(sorted(SUPPORTED_PROTOCOLS))}."
            )

        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Invalid port in proxy string '{cleaned}'.") from exc

        host = parsed.hostname
        if not host or port is None:
            raise ValueError(f"Invalid proxy URL '{cleaned}': host and port are required.")

        if not (1 <= port <= 65535):
            raise ValueError(f"Port {port} out of valid range (1-65535).")

        username = unquote(parsed.username) if parsed.username is not None else None
        password = unquote(parsed.password) if parsed.password is not None else None

        return {
            "raw_proxy": cleaned,
            "protocol": protocol,
            "host": host,
            "port": int(port),
            "username": username,
            "password": password,
        }

    # No scheme prefix
    if "@" in cleaned:
        # Handle user:pass@host:port without protocol
        parsed = urlparse(f"http://{cleaned}")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(f"Invalid port in proxy string '{cleaned}'.") from exc

        host = parsed.hostname
        if not host or port is None or not (1 <= port <= 65535):
            raise ValueError(f"Invalid proxy format '{cleaned}'.")

        username = unquote(parsed.username) if parsed.username is not None else None
        password = unquote(parsed.password) if parsed.password is not None else None

        return {
            "raw_proxy": cleaned,
            "protocol": "http",
            "host": host,
            "port": int(port),
            "username": username,
            "password": password,
        }

    parts = cleaned.split(":")
    if len(parts) == 2:
        host, port_str = parts
        username, password = None, None
    elif len(parts) == 4:
        host, port_str, username, password = parts
        username = username or None
        password = password or None
    else:
        raise ValueError(
            f"Invalid proxy format '{cleaned}'. Expected 'host:port', 'host:port:user:pass', "
            "or 'protocol://[user:pass@]host:port'."
        )

    host = host.strip()
    if not host:
        raise ValueError(f"Host cannot be empty in proxy '{cleaned}'.")

    try:
        port = int(port_str.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid port '{port_str}' in proxy '{cleaned}'.") from exc

    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} out of valid range (1-65535).")

    return {
        "raw_proxy": cleaned,
        "protocol": "http",
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


def _extract_proxy_fields(proxy_data: Union[Proxy, Dict[str, Any]]) -> Tuple[str, str, int, Optional[str], Optional[str]]:
    """Extract normalized fields from either a Proxy ORM instance or dict."""
    if isinstance(proxy_data, dict):
        protocol = str(proxy_data.get("protocol") or "http").lower()
        host = str(proxy_data["host"])
        port = int(proxy_data["port"])
        username = proxy_data.get("username")
        password = proxy_data.get("password")
    else:
        protocol = str(proxy_data.protocol or "http").lower()
        host = str(proxy_data.host)
        port = int(proxy_data.port)
        username = proxy_data.username
        password = proxy_data.password

    return protocol, host, port, username, password


def to_playwright_proxy(proxy_data: Union[Proxy, Dict[str, Any]]) -> Dict[str, str]:
    """Convert Proxy model or dict into Playwright proxy configuration dict."""
    protocol, host, port, username, password = _extract_proxy_fields(proxy_data)
    result: Dict[str, str] = {"server": f"{protocol}://{host}:{port}"}
    if username:
        result["username"] = str(username)
    if password:
        result["password"] = str(password)
    return result


def to_httpx_proxy_url(proxy_data: Union[Proxy, Dict[str, Any]]) -> str:
    """Build proxy URL string suitable for httpx.AsyncClient."""
    protocol, host, port, username, password = _extract_proxy_fields(proxy_data)
    if username and password:
        user_enc = quote(str(username), safe="")
        pass_enc = quote(str(password), safe="")
        return f"{protocol}://{user_enc}:{pass_enc}@{host}:{port}"
    if username:
        user_enc = quote(str(username), safe="")
        return f"{protocol}://{user_enc}@{host}:{port}"
    return f"{protocol}://{host}:{port}"


async def check_proxy_connectivity(
    proxy_data: Union[Proxy, Dict[str, Any]],
    timeout: float = 10.0,
) -> Tuple[bool, Optional[int], Optional[str]]:
    """Check if proxy is reachable and measure response latency in milliseconds.

    Args:
        proxy_data: Proxy ORM instance or parsed proxy dict.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (is_working, latency_ms, error_message).
    """
    try:
        proxy_url = to_httpx_proxy_url(proxy_data)
    except Exception as exc:
        return False, None, f"Invalid proxy configuration: {exc}"

    test_url = "https://api.ipify.org?format=json"
    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            response = await client.get(test_url)
            response.raise_for_status()
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return True, latency_ms, None
    except Exception as exc:
        return False, None, str(exc)
