from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from config.settings import settings

# Use DuckDuckGo's canonical HTML endpoint directly. The shorter hostname
# responds with a body-less redirect and releases its TLS socket before
# requests exposes the response, so the connected-peer SSRF check cannot
# verify it and correctly fails closed.
SEARCH_URL = "https://html.duckduckgo.com/html/"
MAX_RESULTS_PER_QUERY = 5
REQUEST_DELAY_SECONDS = 4
MAX_REDIRECTS = 5
ALLOWED_REMOTE_PORTS = {80, 443}
PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}

DOWNLOAD_DIR = Path(settings.UPLOAD_FOLDER).resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
})


class UnsafeRemoteURL(ValueError):
    """A URL that must never be fetched or retried."""


def _reject_non_public_ip(address: str) -> None:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeRemoteURL("Connected peer returned an invalid IP address") from exc
    if not ip.is_global:
        raise UnsafeRemoteURL(f"Blocked non-public destination: {ip}")


def validate_public_url(url: str) -> str:
    """Resolve a URL and reject credentials, local names, and every non-global IP."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(char) < 32 for char in url):
        raise UnsafeRemoteURL("URL is malformed or too long")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeRemoteURL("Only HTTP(S) URLs are supported")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeRemoteURL("URL host is invalid")
    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeRemoteURL("URL host is invalid") from exc
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise UnsafeRemoteURL("Local destinations are blocked")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeRemoteURL("URL port is invalid") from exc
    if port not in ALLOWED_REMOTE_PORTS:
        raise UnsafeRemoteURL("Only remote ports 80 and 443 are allowed")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise UnsafeRemoteURL("Destination host could not be resolved") from exc
    if not addresses:
        raise UnsafeRemoteURL("Destination host has no routable address")
    for address in addresses:
        _reject_non_public_ip(address)
    return url


def _validate_connected_peer(response: requests.Response) -> None:
    raw = getattr(response, "raw", None)
    if raw is None:
        raise UnsafeRemoteURL("Could not verify the connected peer address")
    connection = getattr(raw, "_connection", None) or getattr(raw, "connection", None)
    sockets = [
        getattr(connection, "sock", None),
        getattr(getattr(getattr(getattr(raw, "_fp", None), "fp", None), "raw", None), "_sock", None),
    ]
    sock = next((candidate for candidate in sockets if candidate is not None), None)
    if sock is None:
        raise UnsafeRemoteURL("Could not verify the connected peer address")
    try:
        peer_address = sock.getpeername()[0]
    except (OSError, TypeError, IndexError) as exc:
        raise UnsafeRemoteURL("Could not verify the connected peer address") from exc
    _reject_non_public_ip(peer_address)


def request_with_retry(url, *, params=None, stream=False, timeout=25, attempts=3):
    """Fetch a public URL with bounded retries and manually validated redirects."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            current_url = validate_public_url(url)
            response: requests.Response | None = None
            for redirect_index in range(MAX_REDIRECTS + 1):
                # Keep the connection open until its peer address is verified.
                response = SESSION.get(
                    current_url,
                    params=params if redirect_index == 0 else None,
                    stream=True,
                    timeout=timeout,
                    allow_redirects=False,
                )
                try:
                    _validate_connected_peer(response)
                except UnsafeRemoteURL:
                    response.close()
                    raise
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                if redirect_index >= MAX_REDIRECTS:
                    response.close()
                    raise UnsafeRemoteURL("Too many redirects")
                location = response.headers.get("Location", "")
                response.close()
                if not location:
                    raise UnsafeRemoteURL("Redirect response is missing Location")
                current_url = validate_public_url(urljoin(response.url or current_url, location))
            if response is None:
                raise RuntimeError("No HTTP response received")
            if response.status_code == 429:
                response.close()
                raise requests.HTTPError("Remote service rate limited the request")
            if 400 <= response.status_code < 500:
                status = response.status_code
                response.close()
                raise UnsafeRemoteURL(f"Remote server rejected the request ({status})")
            try:
                response.raise_for_status()
            except requests.RequestException:
                response.close()
                raise
            if not stream:
                _ = response.content
            return response
        except UnsafeRemoteURL:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(REQUEST_DELAY_SECONDS * attempt)
    raise last_error or RuntimeError("Unable to connect")


def extract_duckduckgo_url(raw_href: str) -> str:
    parsed = urlparse(raw_href)
    query = parse_qs(parsed.query)
    return unquote(query["uddg"][0]) if "uddg" in query else raw_href


def _parse_duckduckgo_results(html: str) -> list[str]:
    hrefs: list[str] = []
    hrefs.extend(re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html))
    hrefs.extend(re.findall(r'<a[^>]+data-testid="result-title-a"[^>]+href="([^"]+)"', html))
    hrefs.extend(re.findall(r'<a[^>]+class="[^"]*result[^"]*"[^>]+href="([^"]+)"', html))
    seen: set[str] = set()
    decoded: list[str] = []
    for href in hrefs:
        url = extract_duckduckgo_url(href.replace("&amp;", "&")).split("#", 1)[0]
        if url not in seen:
            seen.add(url)
            decoded.append(url)
    return decoded


def search_pdf_urls(query, max_results=MAX_RESULTS_PER_QUERY):
    response = request_with_retry(SEARCH_URL, params={"q": query, "kl": "us-en"})
    try:
        pdf_urls: list[str] = []
        for url in _parse_duckduckgo_results(response.text):
            if ".pdf" not in url.lower():
                continue
            try:
                validate_public_url(url)
            except ValueError:
                continue
            pdf_urls.append(url)
            if len(pdf_urls) >= max_results:
                break
        return pdf_urls
    finally:
        response.close()


def safe_pdf_filename(url):
    parsed = urlparse(url)
    file_name = unquote(os.path.basename(parsed.path)) or "document.pdf"
    if not file_name.lower().endswith(".pdf"):
        file_name += ".pdf"
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in file_name)[:180]


def download_pdf(url, file_path):
    validate_public_url(url)
    response = request_with_retry(url, stream=True)
    temp_path = Path(file_path).with_suffix(Path(file_path).suffix + ".part")
    try:
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        content_type = content_type.split(";", 1)[0].strip().lower()
        if content_type not in PDF_CONTENT_TYPES:
            raise ValueError("URL did not return an allowed PDF content type")
        try:
            content_length = int(response.headers.get("Content-Length", "0") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Remote PDF has an invalid Content-Length") from exc
        if content_length < 0 or content_length > settings.MAX_UPLOAD_BYTES:
            raise ValueError("PDF is too large")

        total = 0
        first_chunk = b""
        with temp_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                if not first_chunk:
                    first_chunk = chunk[:8]
                total += len(chunk)
                if total > settings.MAX_UPLOAD_BYTES:
                    raise ValueError("PDF is too large")
                output.write(chunk)
        if not first_chunk.startswith(b"%PDF-"):
            raise ValueError("URL did not return a PDF")
        temp_path.replace(file_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        response.close()
