#!/usr/bin/env python3
"""Check the external citations used by Mokha Caffè articles."""

import argparse
import http.client
import ipaddress
import json
import socket
import ssl
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse


SITE_HOSTS = {"mokhacaffe.com", "www.mokhacaffe.com"}
BROKEN_STATUSES = {404, 410}


def contains_article(value):
    if isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "Article" in types:
            return True
        return any(contains_article(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_article(child) for child in value)
    return False


@dataclass(frozen=True)
class CheckResult:
    url: str
    pages: tuple
    status: int
    final_url: str
    level: str


class ArticleLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = []
        self.is_article = False
        self._jsonld = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.anchors.append(attributes["href"])
        elif tag == "script" and attributes.get("type") == "application/ld+json":
            self._jsonld = ""

    def handle_data(self, data):
        if self._jsonld is not None:
            self._jsonld += data

    def handle_endtag(self, tag):
        if tag != "script" or self._jsonld is None:
            return
        try:
            self.is_article = self.is_article or contains_article(json.loads(self._jsonld))
        except json.JSONDecodeError:
            pass
        self._jsonld = None


def collect_source_links(pages):
    links = {}
    for page_name, html in pages.items():
        parser = ArticleLinkParser()
        parser.feed(html)
        if not parser.is_article:
            continue
        for href in parser.anchors:
            parsed = urlparse(href)
            host = (parsed.hostname or "").lower()
            if parsed.scheme in {"http", "https"} and host and host not in SITE_HOSTS:
                links.setdefault(href, []).append(page_name)
    return links


def article_pages_without_sources(pages, links):
    linked_pages = {page for source_pages in links.values() for page in source_pages}
    missing = []
    for page_name, html in pages.items():
        parser = ArticleLinkParser()
        parser.feed(html)
        if parser.is_article and page_name not in linked_pages:
            missing.append(page_name)
    return missing


def check_links(links, fetcher):
    results = []
    for url, pages in links.items():
        status, final_url = fetcher(url)
        if status in BROKEN_STATUSES:
            level = "FAIL"
        elif 400 <= status < 500 or status == 0 or status >= 500:
            level = "WARN"
        else:
            level = "ok" if 200 <= status < 400 else "FAIL"
        results.append(CheckResult(url, tuple(pages), status, final_url, level))
    return results


def resolved_public_address(url):
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("source URL must have an HTTP(S) host and no credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise OSError("source host did not resolve")
    resolved = [address[4][0] for address in addresses]
    if not all(ipaddress.ip_address(address).is_global for address in resolved):
        raise ValueError("source host resolves to a non-public address")
    return resolved[0]


def request_once(url, address):
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host = parsed.hostname
    host_header = host if port in {80, 443} else f"{host}:{port}"
    sock = socket.create_connection((address, port), timeout=20)
    try:
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "User-Agent: MokhaCaffe-source-check/1.0 (read-only; contact hello@mokhacaffe.com)\r\n"
            "Accept: text/html,application/xhtml+xml;q=0.9,*/*;q=0.1\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = http.client.HTTPResponse(sock)
        response.begin()
        location = response.getheader("Location")
        final_url = urljoin(url, location) if location else url
        response.close()
        return response.status, final_url
    finally:
        sock.close()


def fetch_url(url):
    request_url, _ = urldefrag(url)
    try:
        address = resolved_public_address(request_url)
        return request_once(request_url, address)
    except (OSError, ValueError, http.client.HTTPException, ssl.SSLError):
        return 0, request_url


def run(pages, fetcher=fetch_url):
    links = collect_source_links(pages)
    missing_pages = article_pages_without_sources(pages, links)
    results = check_links(links, fetcher)
    for result in results:
        pages_text = ", ".join(result.pages)
        print(f"[{result.level}] HTTP {result.status or 'error'} {result.url} ({pages_text})")
    for page in missing_pages:
        print(f"[WARN] {page} has no external source link")
    failures = sum(result.level == "FAIL" for result in results)
    warnings = sum(result.level == "WARN" for result in results) + len(missing_pages)
    print(f"{len(results)} external article sources checked: {failures} FAIL, {warnings} WARN")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, default=Path(__file__).parents[1] / "public")
    args = parser.parse_args()
    pages = {
        str(path.relative_to(args.public)): path.read_text()
        for path in sorted(args.public.rglob("index.html"))
    }
    return run(pages)


if __name__ == "__main__":
    sys.exit(main())
