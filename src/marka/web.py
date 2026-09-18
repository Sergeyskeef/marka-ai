"""Bounded public HTTPS retrieval. DNS is validated and pinned for the connection."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.message import Message
import http.client
import ipaddress
import re
import socket
import ssl
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser


class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global or ipaddress.ip_address(entry[4][0]).is_multicast for entry in addresses):
            raise ValueError("Only public Internet addresses are allowed")
        last_error = None
        for family, kind, proto, _, address in addresses[:2]:
            raw = socket.socket(family, kind, proto)
            raw.settimeout(self.timeout)
            try:
                raw.connect(address)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as exc:
                last_error = exc
                raw.close()
        raise OSError("Public website could not be reached") from last_error


class TextOnly(HTMLParser):
    def __init__(self, base_url=""):
        super().__init__()
        self.parts = []
        self.hidden = 0
        self.base_url = base_url
        self.links = []
        self.link_chars = 0
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "a" and not self.hidden:
            self._anchor = None
            href = dict(attrs).get("href")
            if isinstance(href, str) and len(self.links) < 30 and not any(ord(c) < 32 for c in href):
                try:
                    url = urllib.parse.urljoin(self.base_url, href.strip())
                    parsed = urllib.parse.urlsplit(url)
                    valid = (len(url) <= 4000 and not any(ord(c) < 32 for c in url)
                             and parsed.scheme == "https" and bool(parsed.hostname)
                             and parsed.username is None and parsed.password is None and parsed.port in {None, 443}
                             and not any(c.isspace() for c in parsed.hostname))
                    if valid:
                        parsed.hostname.encode("idna")
                except (ValueError, UnicodeError):
                    valid = False
                if valid and self.link_chars + len(url) <= 6000 and not any(link["url"] == url for link in self.links):
                    self._anchor = {"url": url, "text": ""}
                    self.links.append(self._anchor)
                    self.link_chars += len(url)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "a":
            self._anchor = None

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self._anchor is not None:
                self._anchor["text"] = (self._anchor["text"] + " " + data.strip()).strip()[:200]


def download(url: str, redirects=3) -> tuple[bytes, str, str]:
    if not isinstance(url, str) or len(url) > 4000 or any(ord(c) < 32 for c in url):
        raise ValueError("Invalid URL")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("Use a public HTTPS URL on port 443, without credentials")
    host = parsed.hostname.encode("idna").decode("ascii")
    connection = PublicHTTPS(host, timeout=15)
    try:
        path = urllib.parse.quote(urllib.parse.unquote(parsed.path or "/"), safe="/%:@!$&'()*+,;=-._~")
        if parsed.query:
            path += "?" + urllib.parse.quote(parsed.query, safe="=%&+;/:?@!$'()*,-._~")
        connection.request("GET", path, headers={"User-Agent": "MarkaAI/2.0 (personal research)", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            if redirects <= 0:
                raise ValueError("Too many redirects")
            return download(urllib.parse.urljoin(url, response.getheader("Location", "")), redirects - 1)
        if response.status != 200:
            raise ValueError(f"Website returned HTTP {response.status}")
        content_type = response.getheader("Content-Type", "")
        if not any(t in content_type.lower() for t in ("text/", "json", "xml")):
            raise ValueError("Only text, JSON, and XML pages can be read")
        deadline = time.monotonic() + 20
        chunks = []
        size = 0
        while size <= 524288:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Website read deadline exceeded")
            if connection.sock is not None:
                connection.sock.settimeout(min(5, remaining))
            chunk = response.read1(min(16384, 524289 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        payload = b"".join(chunks)
        if len(payload) > 524288:
            raise ValueError("Page exceeds 512 KiB limit")
        return payload, content_type, url
    finally:
        connection.close()


def fetch(url: str, offset: int = 0, expected_sha256: str = "") -> dict:
    if type(offset) is not int or offset < 0:
        raise ValueError("Page offset must be a nonnegative character position")
    if not isinstance(expected_sha256, str) or (expected_sha256 and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("Expected source SHA256 must be a lowercase hexadecimal digest")
    body, content_type, final_url = download(url)
    digest = hashlib.sha256(body).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Web source changed since the previous page; refetch from offset 0")
    message = Message()
    message["Content-Type"] = content_type
    encoding = message.get_content_charset() or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except (LookupError, UnicodeError, ValueError, TypeError):
        encoding, text = "utf-8", body.decode("utf-8", errors="replace")
    links = []
    if "html" in content_type.lower():
        parser = TextOnly(final_url)
        parser.feed(text)
        parser.close()
        text = "\n".join(parser.parts)
        links = parser.links
    end = min(len(text), offset + 14000)
    return {"url": final_url, "content": text[offset:end], "truncated": bool(offset or end < len(text)),
            "offset": offset, "total_chars": len(text), "next_offset": end if end < len(text) else None,
            "sha256": digest, "fetched_at": datetime.now(timezone.utc).isoformat(), "encoding": encoding,
            "links": links, "trust": "untrusted_external_source"}


def search(query: str) -> dict:
    if not 1 <= len(query) <= 500:
        raise ValueError("Search query must contain 1–500 characters")
    body, _, _ = download("https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query))
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise ValueError("Search provider returned invalid XML; no search results were verified") from None
    results = [{"title": item.findtext("title", ""), "url": item.findtext("link", ""),
                "snippet": item.findtext("description", "")[:800]} for item in root.findall("./channel/item")[:6]]
    return {"results": results, "provider": "Bing public RSS; availability is best effort", "trust": "untrusted_search_snippets"}
