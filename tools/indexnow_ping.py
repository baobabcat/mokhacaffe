#!/usr/bin/env python3
"""Ping IndexNow (Bing/Yandex/DDG-via-Bing instant indexing) with the site's sitemap URLs.

Key model (https://www.indexnow.org/documentation):
  - A key file <KEY>.txt containing <KEY> must be served at the site root.
  - POST https://api.indexnow.org/indexnow with JSON {host, key, keyLocation, urlList}.
  - No account or interactive login required.

Usage: python3 tools/indexnow_ping.py [--dry-run]
Reads the key from the single hex-named .txt file in public/ and URLs from public/sitemap.xml.
Exit 0 on HTTP 200/202 (accepted), 1 otherwise.
"""
import glob
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
HOST = "mokhacaffe.com"
ENDPOINT = "https://api.indexnow.org/indexnow"


def find_key() -> str:
    candidates = [
        p for p in glob.glob(str(PUBLIC / "*.txt"))
        if re.fullmatch(r"[0-9a-f]{32}", Path(p).stem)
    ]
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly 1 IndexNow key file, found {candidates}")
    key = Path(candidates[0]).stem
    body = Path(candidates[0]).read_text().strip()
    if body != key:
        raise SystemExit("key file content does not match filename")
    return key


def sitemap_urls() -> list[str]:
    tree = ET.parse(PUBLIC / "sitemap.xml")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [(loc.text or "").strip() for loc in tree.findall(".//sm:loc", ns) if loc.text]


def main() -> int:
    dry = "--dry-run" in sys.argv
    key = find_key()
    urls = sitemap_urls()
    payload = {
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
        "urlList": urls,
    }
    print(f"key={key} urls={len(urls)} keyLocation={payload['keyLocation']}")
    for u in urls:
        print(f"  {u}")
    if dry:
        print("dry-run: not posting")
        return 0
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            body = resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode(errors="replace")
    print(f"HTTP {status} {body.strip()}")
    # 200 = submitted, 202 = accepted-pending-key-validation; both are success.
    return 0 if status in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
