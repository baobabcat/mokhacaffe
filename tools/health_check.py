#!/usr/bin/env python3
"""Read-only production health check for mokhacaffe.com."""

from pathlib import Path
import sys
from typing import NamedTuple
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "public" / "sitemap.xml"
ORIGIN = "https://mokhacaffe.com"
USER_AGENT = "MokhaVerification/1.0 (read-only; contact hello@mokhacaffe.com)"


class Response(NamedTuple):
    status: int
    headers: object
    body: bytes
    final_url: str | None = None


class Check(NamedTuple):
    label: str
    url: str
    expected_status: int


def build_checks(canonical_urls):
    """Build health checks from the canonical sitemap route set."""
    checks = [Check(f"canonical:{url}", url, 200) for url in canonical_urls]
    checks.extend(
        [
            Check("sitemap", f"{ORIGIN}/sitemap.xml", 200),
            Check("atom-feed", f"{ORIGIN}/feed.xml", 200),
            Check("robots", f"{ORIGIN}/robots.txt", 200),
            Check("og-image", f"{ORIGIN}/assets/og.png", 200),
            Check("favicon", f"{ORIGIN}/assets/favicon.svg", 200),
            Check("ratio-calculator-module", f"{ORIGIN}/assets/ratio-calculator.mjs", 200),
            Check(
                "ratio-calculator-page-module",
                f"{ORIGIN}/assets/ratio-calculator-page.mjs",
                200,
            ),
            Check(
                "indexnow-key",
                f"{ORIGIN}/79ab30351487365090c7d6b534c3dbb4.txt",
                200,
            ),
            Check("branded-404", f"{ORIGIN}/nope-404", 404),
        ]
    )
    return checks


def fetch(url, opener=urllib.request.urlopen):
    """Fetch a health target with an identifiable first-party user agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=20) as response:
            return Response(
                response.status,
                response.headers,
                response.read(),
                response.geturl(),
            )
    except urllib.error.HTTPError as error:
        return Response(error.code, error.headers, error.read(), error.geturl())


def validate_home(response):
    """Check homepage content and the security header used by the daily probe."""
    failures = []
    if b"Mokha" not in response.body:
        failures.append("home-marker: 'Mokha' not found in homepage HTML")
    if b"beacon.min.js" not in response.body:
        failures.append("beacon: cloudflare web-analytics beacon missing from homepage")
    headers = {str(key).lower(): value for key, value in response.headers.items()}
    if "strict-transport-security" not in headers:
        failures.append("hsts: strict-transport-security header missing")
    return failures


def run_checks(checks, fetcher=fetch):
    """Run status checks and return human-readable failures."""
    failures = []
    for check in checks:
        try:
            response = fetcher(check.url)
        except urllib.error.URLError as error:
            failures.append(
                f"{check.label}: request failed: {error.reason} ({check.url})"
            )
            continue
        if response.status != check.expected_status:
            failures.append(
                f"{check.label}: got HTTP {response.status}, expected "
                f"{check.expected_status} ({check.url})"
            )
        elif response.final_url and response.final_url != check.url:
            failures.append(
                f"{check.label}: resolved to {response.final_url}, expected {check.url}"
            )
        elif check.label == "branded-404" and b"Lost off" not in response.body:
            failures.append(
                "branded-404: expected branded 404 body marker 'Lost off'"
            )
    return failures


def check_site(sitemap_path=SITEMAP, fetcher=fetch):
    """Run the sitemap-derived production matrix and homepage invariants."""
    checks = build_checks(sitemap_urls(sitemap_path))
    failures = run_checks(checks, fetcher=fetcher)
    try:
        home = fetcher(f"{ORIGIN}/")
    except urllib.error.URLError as error:
        failures.append(f"home-invariants: request failed: {error.reason} ({ORIGIN}/)")
    else:
        failures.extend(validate_home(home))
    return failures


def sitemap_urls(path=SITEMAP):
    """Return HTTPS Mokha canonical URLs from the deployable sitemap."""
    tree = ET.parse(path)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if tree.getroot().tag != f"{{{namespace['s']}}}urlset":
        raise ValueError("expected a sitemap urlset")
    urls = []
    for loc in tree.findall(".//s:loc", namespace):
        if not loc.text:
            continue
        url = loc.text.strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "mokhacaffe.com":
            raise ValueError(f"unexpected sitemap origin: {url}")
        urls.append(url)
    if not urls:
        raise ValueError("sitemap contains no canonical URLs")
    return urls


def main():
    failures = check_site()
    if failures:
        print("mokhacaffe.com health check FAILED", file=sys.stderr)
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
