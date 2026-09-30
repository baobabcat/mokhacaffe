#!/usr/bin/env python3
"""Bing Webmaster API client for mokhacaffe.com (JSON API, no dependencies).

Rationale: the site was verified in Bing Webmaster Tools by the owner on
2026-08-31. With an API key (BWT dashboard -> Settings -> API access) this
tool gives the lab VM two things it currently lacks:
  1. Programmatic URL submission (SubmitUrlBatch) — replaces the IndexNow
     experiment, which was judged ineffective here pre-verification.
  2. Verifiable indexing telemetry (GetUrlInfo / GetCrawlStats /
     GetQueryStats / GetPageStats / GetRankAndTrafficStats) — today the only
     VM-reachable indexing signal is edge crawler user-agents.

Key handling: the key is read ONLY from the BING_WEBMASTER_API_KEY environment
variable. It is never written to disk by this tool and never printed.

API reference (verified 2026-09-01 against Microsoft Learn, generated from
Microsoft.Bing.Webmaster.Api.Interfaces.IWebmasterApi):
  base   https://ssl.bing.com/webmaster/api.svc/json/<Method>
  GET    ?siteUrl=<site>&apikey=<key>            (read methods)
  GET    ?siteUrl=<site>&url=<url>&apikey=<key>  (GetUrlInfo)
  POST   ?apikey=<key>, JSON body                 (SubmitUrl / SubmitUrlBatch)
         SubmitUrl      {"siteUrl": ..., "url": ...}
         SubmitUrlBatch {"siteUrl": ..., "urlList": [...]}

Usage:
  python3 tools/bing_webmaster.py sites                 # list verified sites (key smoke test)
  python3 tools/bing_webmaster.py quota                 # URL-submission quota left today
  python3 tools/bing_webmaster.py submit [--sitemap] [URL ...]
  python3 tools/bing_webmaster.py urlinfo <URL>
  python3 tools/bing_webmaster.py search-summary
  python3 tools/bing_webmaster.py crawl-stats|query-stats|page-stats|rank-traffic

Exit codes: 0 success, 1 API/transport error, 2 usage/config error.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "public" / "sitemap.xml"
BASE = "https://ssl.bing.com/webmaster/api.svc/json"
SITE = "https://mokhacaffe.com/"
UA = "mokhacaffe-ops/1.0 (+https://mokhacaffe.com; AI-operated)"
MICROSOFT_DATE = re.compile(r"^/Date\((-?\d+)\)/$")


def get_key() -> str:
    key = os.environ.get("BING_WEBMASTER_API_KEY", "").strip()
    if not key:
        sys.exit(
            "error: BING_WEBMASTER_API_KEY is not set.\n"
            "Generate one in Bing Webmaster Tools -> Settings -> API access,\n"
            "then export it (never commit it)."
        )
    return key


def call(method: str, params: dict | None = None, body: dict | None = None) -> dict:
    key = get_key()
    q = {"apikey": key}
    if params:
        q.update(params)
    url = f"{BASE}/{method}?{urllib.parse.urlencode(q)}"
    data = None
    headers = {"User-Agent": UA}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    payload = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read().decode()
            break
        except urllib.error.HTTPError as e:
            try:
                raw_detail = e.read().decode(errors="replace")
            finally:
                e.close()
            detail = raw_detail[:300]
            if e.code in (401, 403) or "InvalidApiKey" in raw_detail:
                sys.exit(f"error: HTTP {e.code} — API key invalid or not authorized for this site.")
            if e.code == 400 and "ThrottleHost" in raw_detail and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            sys.exit(f"error: HTTP {e.code} from {method}: {detail}")
        except urllib.error.URLError as e:
            sys.exit(f"error: transport failure calling {method}: {e.reason}")
    try:
        out = json.loads(payload)
    except json.JSONDecodeError:
        sys.exit(f"error: non-JSON response from {method}: {payload[:200]}")
    if isinstance(out, dict) and out.get("ErrorCode"):
        sys.exit(f"error: API {method} returned ErrorCode={out.get('ErrorCode')}: {out.get('Message')}")
    return out


def sitemap_urls() -> list[str]:
    tree = ET.parse(SITEMAP)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in tree.findall(".//s:loc", ns) if loc.text]


def readable_dates(value):
    """Convert Microsoft's JSON millisecond dates to explicit UTC ISO strings."""
    if isinstance(value, dict):
        return {key: readable_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [readable_dates(item) for item in value]
    if isinstance(value, str) and (match := MICROSOFT_DATE.fullmatch(value)):
        try:
            instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                milliseconds=int(match.group(1))
            )
        except (ValueError, OverflowError):
            return value
        return instant.isoformat().replace("+00:00", "Z")
    return value


def cmd_sites(_):
    sites = call("GetUserSites").get("d", [])
    for s in sites:
        print(s.get("Url", s))
    if not sites:
        print("(no sites returned)")


def cmd_quota(_):
    d = call("GetUrlSubmissionQuota", {"siteUrl": SITE}).get("d", {})
    print(json.dumps(d, indent=2))


def cmd_submit(args):
    urls = list(args.urls)
    if args.sitemap or not urls:
        urls.extend(u for u in sitemap_urls() if u not in urls)
    if not urls:
        sys.exit("error: no URLs to submit (pass URLs or --sitemap).")
    # SubmitUrlBatch accepts a list; chunk conservatively at 100/call.
    submitted = 0
    for i in range(0, len(urls), 100):
        chunk = urls[i : i + 100]
        if args.dry_run:
            print(f"dry-run: would submit {len(chunk)} URL(s): {chunk[0]} ...")
        else:
            call("SubmitUrlBatch", body={"siteUrl": SITE, "urlList": chunk})
            print(f"submitted {len(chunk)} URL(s)")
        submitted += len(chunk)
    print(f"total: {submitted}")


def cmd_urlinfo(args):
    d = call("GetUrlInfo", {"siteUrl": SITE, "url": args.url}).get("d", {})
    print(json.dumps(readable_dates(d), indent=2))


def _stats_summary(rows):
    """Summarize every dated click/impression row returned by Bing."""
    if not rows or not all(
        isinstance(row, dict)
        and isinstance(row.get("Clicks"), (int, float))
        and isinstance(row.get("Impressions"), (int, float))
        for row in rows
    ):
        return None
    dates = sorted(
        converted
        for row in rows
        if isinstance((converted := readable_dates(row.get("Date"))), str)
        and converted != row.get("Date")
    )
    if not dates:
        return None
    clicks = sum(row["Clicks"] for row in rows)
    impressions = sum(row["Impressions"] for row in rows)
    click_label = "click" if clicks == 1 else "clicks"
    impression_label = "impression" if impressions == 1 else "impressions"
    position = ""
    if impressions > 0 and all(
        isinstance(row.get("AvgImpressionPosition"), (int, float)) for row in rows
    ):
        weighted_position = sum(
            row["AvgImpressionPosition"] * row["Impressions"] for row in rows
        ) / impressions
        position = f", impression-weighted position {weighted_position:.1f}"
    return (
        f"summary: {len(rows)} rows, {impressions:g} {impression_label}, "
        f"{clicks:g} {click_label}{position}, {dates[0]} to {dates[-1]}"
    )


def _stats_totals(rows):
    if not isinstance(rows, list) or not all(
        isinstance(row, dict)
        and isinstance(row.get("Clicks"), (int, float))
        and isinstance(row.get("Impressions"), (int, float))
        for row in rows
    ):
        sys.exit("error: Bing returned an invalid search-stat response.")
    return (
        sum(row["Clicks"] for row in rows),
        sum(row["Impressions"] for row in rows),
    )


def cmd_search_summary(_):
    reports = {
        method: call(method, {"siteUrl": SITE}).get("d", [])
        for method in (
            "GetRankAndTrafficStats",
            "GetQueryStats",
            "GetPageStats",
        )
    }
    aggregate_clicks, aggregate_impressions = _stats_totals(
        reports["GetRankAndTrafficStats"]
    )
    query_clicks, query_impressions = _stats_totals(reports["GetQueryStats"])
    page_clicks, page_impressions = _stats_totals(reports["GetPageStats"])

    def detail_line(label, clicks, impressions):
        coverage = (
            f" ({impressions / aggregate_impressions:.1%} of aggregate)"
            if aggregate_impressions
            else ""
        )
        return f"{label}: {impressions:g} impressions{coverage}, {clicks:g} clicks"

    print(f"aggregate: {aggregate_impressions:g} impressions, {aggregate_clicks:g} clicks")
    print(detail_line("visible queries", query_clicks, query_impressions))
    print(detail_line("visible pages", page_clicks, page_impressions))
    for label, impressions in (
        ("query", query_impressions),
        ("page", page_impressions),
    ):
        omitted = max(0, aggregate_impressions - impressions)
        noun = "impression" if omitted == 1 else "impressions"
        print(f"omitted from {label} details: {omitted:g} {noun}")

    query_rows = reports["GetQueryStats"]
    if query_impressions and all(
        isinstance(row.get("AvgImpressionPosition"), (int, float))
        for row in query_rows
    ):
        position = sum(
            row["AvgImpressionPosition"] * row["Impressions"] for row in query_rows
        ) / query_impressions
        print(f"visible impression-weighted position: {position:.1f}")


def _stats(method):
    d = call(method, {"siteUrl": SITE}).get("d", [])
    if isinstance(d, list):
        print(f"{method}: {len(d)} rows")
        if summary := _stats_summary(d):
            print(summary)
        for row in d[:20]:
            print(json.dumps(readable_dates(row)))
        if len(d) > 20:
            print(f"... {len(d) - 20} more")
    else:
        print(json.dumps(readable_dates(d), indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sites", help="list sites visible to this API key")
    sub.add_parser("quota", help="show remaining URL-submission quota")
    sp = sub.add_parser("submit", help="submit URLs (default: all sitemap URLs)")
    sp.add_argument("urls", nargs="*")
    sp.add_argument("--sitemap", action="store_true", help="include all sitemap URLs")
    sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("urlinfo", help="Bing's stored info for one URL")
    sp.add_argument("url")
    sub.add_parser(
        "search-summary",
        help="reconcile aggregate, query, and page search totals",
    )
    for name, method in [
        ("crawl-stats", "GetCrawlStats"),
        ("query-stats", "GetQueryStats"),
        ("page-stats", "GetPageStats"),
        ("rank-traffic", "GetRankAndTrafficStats"),
    ]:
        p = sub.add_parser(name, help=method)
        p.set_defaults(_method=method)
    args = ap.parse_args()
    dispatch = {
        "sites": cmd_sites,
        "quota": cmd_quota,
        "submit": cmd_submit,
        "urlinfo": cmd_urlinfo,
        "search-summary": cmd_search_summary,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        _stats(args._method)


if __name__ == "__main__":
    main()
