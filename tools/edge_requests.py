#!/usr/bin/env python3
"""Mokha Caffè edge-request baseline via Cloudflare GraphQL (server-side).

Complements rum_baseline.py: the RUM beacon only fires on real browsers that
execute JS — crawlers, feed readers, and HEAD/GET bots are invisible there.
This tool counts actual edge requests for the zone, grouped by path, method,
status, and user agent. It separately counts successful requests to canonical
HTML pages, so scanner probes and asset fetches do not inflate that content
number. It also shows whether search crawlers (Bingbot,
Googlebot, DuckDuckBot, YandexBot) have fetched robots.txt / sitemap.xml /
feed.xml / pages — the leading indicator on the indexing pipeline. Search
Search Console + Bing Webmaster Tools were verified by the owner on 2026-08-31
(sitemap submitted to both). Bing API telemetry is now available from this VM;
edge telemetry still shows crawler requests that browser analytics misses.

Read-only. Requires CLOUDFLARE_API_TOKEN in env (same token as deploys).

Usage: python3 tools/edge_requests.py [--hours 168]
"""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ZONE = "df47a612388511375ea5fc45be07040d"  # mokhacaffe.com (verified 2026-08-31)
GQL = "https://api.cloudflare.com/client/v4/graphql"
GROUP_LIMIT = 500

QUERY = """query($zone: String!, $since: Time!, $until: Time!) {
  viewer { zones(filter: {zoneTag: $zone}) {
    httpRequestsAdaptiveGroups(limit: 500,
        filter: {datetime_geq: $since, datetime_leq: $until}) {
      count
      dimensions {
        clientRequestPath
        edgeResponseStatus
        clientRequestHTTPMethodName
        userAgent
      }
    } } } }"""

BOT_UAS = ("googlebot", "bingbot", "duckduckbot", "yandexbot", "baiduspider",
           "slurp", "applebot", "petalbot", "seznambot", "gptbot",
           "claudebot", "perplexitybot", "bytespider")
SEARCH_CRAWLER_UAS = ("googlebot", "bingbot", "duckduckbot", "yandexbot")
FEED_READER_UAS = (
    "feedbin", "feedly", "freshrss", "inoreader", "miniflux", "netnewswire",
    "newsblur", "the old reader",
)
SITE_CHECK_UAS = ("mokha-seo-audit", "mokhaverification", "mokhareleaseverifier")
ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "public" / "sitemap.xml"


def sitemap_canonical_paths(path=SITEMAP):
    """Return same-origin canonical paths from the deployable sitemap."""
    tree = ET.parse(path)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if tree.getroot().tag != f"{{{namespace['s']}}}urlset":
        raise ValueError("expected a sitemap urlset")
    paths = set()
    for loc in tree.findall(".//s:loc", namespace):
        if not loc.text:
            continue
        url = urllib.parse.urlsplit(loc.text.strip())
        if url.scheme != "https" or url.netloc != "mokhacaffe.com":
            raise ValueError(f"unexpected sitemap origin: {loc.text.strip()}")
        paths.add(url.path or "/")
    if not paths:
        raise ValueError("sitemap contains no canonical URLs")
    return paths


CANONICAL_CONTENT_PATHS = sitemap_canonical_paths()


def merge_group_rows(rows):
    """Merge GraphQL rows while retaining dimensions used by reports."""
    dimensions = (
        "clientRequestPath",
        "edgeResponseStatus",
        "clientRequestHTTPMethodName",
        "userAgent",
    )
    merged = {}
    for row in rows:
        values = row["dimensions"]
        key = tuple(values.get(name) for name in dimensions)
        merged[key] = merged.get(key, 0) + row["count"]
    return [
        {
            "count": count,
            "dimensions": dict(zip(dimensions, key)),
        }
        for key, count in merged.items()
    ]


def canonical_content_requests(groups):
    """Aggregate successful GET/HEAD requests to canonical HTML pages."""
    requests = {}
    for group in groups:
        dimensions = group["dimensions"]
        path = dimensions.get("clientRequestPath")
        if (
            path in CANONICAL_CONTENT_PATHS
            and dimensions.get("edgeResponseStatus") == 200
            and dimensions.get("clientRequestHTTPMethodName") in ("GET", "HEAD")
        ):
            requests[path] = requests.get(path, 0) + group["count"]
    return requests


def canonical_content_request_split(groups):
    """Split canonical requests into known crawlers and all other user agents."""
    crawler = 0
    other = 0
    for group in groups:
        dimensions = group["dimensions"]
        if (
            dimensions.get("clientRequestPath") in CANONICAL_CONTENT_PATHS
            and dimensions.get("edgeResponseStatus") == 200
            and dimensions.get("clientRequestHTTPMethodName") in ("GET", "HEAD")
        ):
            ua = (dimensions.get("userAgent") or "").lower()
            if any(bot in ua for bot in BOT_UAS):
                crawler += group["count"]
            else:
                other += group["count"]
    return crawler, other


def canonical_crawler_requests_by_path(groups):
    """Aggregate known crawler signatures on successful canonical requests."""
    requests = {}
    for group in groups:
        dimensions = group["dimensions"]
        path = dimensions.get("clientRequestPath")
        ua = (dimensions.get("userAgent") or "").lower()
        crawler_name = next((bot for bot in BOT_UAS if bot in ua), None)
        if (
            path in CANONICAL_CONTENT_PATHS
            and dimensions.get("edgeResponseStatus") == 200
            and dimensions.get("clientRequestHTTPMethodName") in ("GET", "HEAD")
            and crawler_name
        ):
            key = (crawler_name, path)
            requests[key] = requests.get(key, 0) + group["count"]
    return requests


def format_acquisition(groups):
    """Format successful canonical-content request counts."""
    content = canonical_content_requests(groups)
    crawler, other = canonical_content_request_split(groups)
    crawler_paths = canonical_crawler_requests_by_path(groups)
    lines = [
        "## canonical content requests",
        f"canonical content requests: {sum(content.values())}",
        f"canonical content requests with a known crawler signature: {crawler}",
        f"other canonical content requests: {other}",
    ]
    for path, count in sorted(content.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"{count:>6}  {path}")
    if crawler_paths:
        lines.append("known crawler signatures by canonical path:")
        for (crawler_name, path), count in sorted(
            crawler_paths.items(), key=lambda item: (-item[1], item[0])
        ):
            lines.append(f"{count:>6}  {crawler_name}  {path}")
    else:
        lines.append("known crawler signatures by canonical path: none observed")
    lines.append(
        "note: other requests are not verified human visits; self traffic and unidentified bots may remain."
    )
    return "\n".join(lines)


def format_search_crawler_coverage(groups):
    """Report canonical-path coverage for the main search crawler signatures."""
    observed = {crawler: set() for crawler in SEARCH_CRAWLER_UAS}
    for group in groups:
        dimensions = group["dimensions"]
        path = dimensions.get("clientRequestPath")
        if (
            path not in CANONICAL_CONTENT_PATHS
            or dimensions.get("edgeResponseStatus") != 200
            or dimensions.get("clientRequestHTTPMethodName") not in ("GET", "HEAD")
        ):
            continue
        ua = (dimensions.get("userAgent") or "").lower()
        for crawler in SEARCH_CRAWLER_UAS:
            if crawler in ua:
                observed[crawler].add(path)
                break

    total = len(CANONICAL_CONTENT_PATHS)
    lines = ["## search crawler canonical-path coverage"]
    for crawler in SEARCH_CRAWLER_UAS:
        paths = sorted(observed[crawler])
        lines.append(f"{crawler}: {len(paths)}/{total} canonical paths observed")
        lines.append("  observed: " + (", ".join(paths) if paths else "none"))
    lines.append(
        "note: user-agent signatures are not verified crawler identities; coverage means observed edge requests, not indexing."
    )
    return "\n".join(lines)


def format_search_crawler_discovery_activity(groups):
    """Report successful discovery and content requests by search crawler."""
    activity = {
        crawler: {"/robots.txt": 0, "/sitemap.xml": 0, "/feed.xml": 0, "canonical": 0}
        for crawler in SEARCH_CRAWLER_UAS
    }
    for group in groups:
        dimensions = group["dimensions"]
        if (
            dimensions.get("edgeResponseStatus") != 200
            or dimensions.get("clientRequestHTTPMethodName") not in ("GET", "HEAD")
        ):
            continue
        ua = (dimensions.get("userAgent") or "").lower()
        crawler = next((name for name in SEARCH_CRAWLER_UAS if name in ua), None)
        if not crawler:
            continue
        path = dimensions.get("clientRequestPath")
        if path in ("/robots.txt", "/sitemap.xml", "/feed.xml"):
            activity[crawler][path] += group["count"]
        elif path in CANONICAL_CONTENT_PATHS:
            activity[crawler]["canonical"] += group["count"]

    lines = ["## search crawler discovery-path activity"]
    for crawler in SEARCH_CRAWLER_UAS:
        counts = activity[crawler]
        lines.append(
            f"{crawler}: robots.txt {counts['/robots.txt']}, "
            f"sitemap.xml {counts['/sitemap.xml']}, feed.xml {counts['/feed.xml']}, "
            f"canonical content {counts['canonical']}"
        )
    lines.append(
        "note: counts include only successful GET/HEAD requests; user-agent signatures are not verified crawler identities."
    )
    return "\n".join(lines)


def format_feed_activity(groups):
    """Classify successful feed requests by broad user-agent signature."""
    counts = {
        "named feed-reader signatures": 0,
        "site checks": 0,
        "known crawler signatures": 0,
        "browser signatures": 0,
        "other or unidentified clients": 0,
    }
    for group in groups:
        dimensions = group["dimensions"]
        if (
            dimensions.get("clientRequestPath") != "/feed.xml"
            or dimensions.get("edgeResponseStatus") != 200
            or dimensions.get("clientRequestHTTPMethodName") not in ("GET", "HEAD")
        ):
            continue
        ua = (dimensions.get("userAgent") or "").lower()
        if any(signature in ua for signature in SITE_CHECK_UAS):
            category = "site checks"
        elif any(signature in ua for signature in BOT_UAS):
            category = "known crawler signatures"
        elif any(signature in ua for signature in FEED_READER_UAS):
            category = "named feed-reader signatures"
        elif "mozilla/" in ua:
            category = "browser signatures"
        else:
            category = "other or unidentified clients"
        counts[category] += group["count"]

    lines = [
        "## feed request activity",
        f"successful feed requests: {sum(counts.values())}",
    ]
    lines.extend(f"{label}: {count}" for label, count in counts.items())
    lines.append(
        "note: user-agent signatures can be spoofed and requests do not prove a subscription or distinct reader."
    )
    return "\n".join(lines)


def guard_group_limit(groups, since, until):
    """Stop when the GraphQL group cap may have omitted low-volume rows."""
    if len(groups) >= GROUP_LIMIT:
        sys.exit(
            f"edge query returned {len(groups)} rows for {since} to {until} "
            f"(limit {GROUP_LIMIT}); refusing to report potentially truncated edge data"
        )


def run(token, since, until):
    body = json.dumps({"query": QUERY,
                       "variables": {"zone": ZONE, "since": since,
                                     "until": until}}).encode()
    req = urllib.request.Request(GQL, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if resp.get("errors"):
        sys.exit(f"GraphQL errors: {resp['errors']}")
    groups = resp["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]
    guard_group_limit(groups, since, until)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=168)
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("CLOUDFLARE_API_TOKEN not set")
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=args.hours)

    # Free-plan quota: httpRequestsAdaptiveGroups windows are capped at 1 day
    # (verified 2026-08-31, GraphQL 'quota' error) — query daily slices and
    # merge. Overlapping boundary rows are double-counted at slice seams; at
    # ~150 req/day this rounding noise is immaterial and stated here.
    rows = []
    cursor = start
    while cursor < now:
        nxt = min(cursor + timedelta(hours=24), now)
        rows.extend(run(token, cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        cursor = nxt
    groups = merge_group_rows(rows)
    total = sum(g["count"] for g in groups)
    print(f"# Edge requests, last {args.hours}h (since "
          f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}) — zone mokhacaffe.com")
    print(f"total edge requests: {total}\n")

    print("## by path (top 25)")
    by_path = {}
    for g in groups:
        p = g["dimensions"]["clientRequestPath"] or "/"
        by_path[p] = by_path.get(p, 0) + g["count"]
    for p, c in sorted(by_path.items(), key=lambda x: -x[1])[:25]:
        print(f"{c:>6}  {p}")

    print("\n## by status")
    by_status = {}
    for g in groups:
        s = g["dimensions"]["edgeResponseStatus"]
        by_status[s] = by_status.get(s, 0) + g["count"]
    for s, c in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"{c:>6}  HTTP {s}")

    print("\n" + format_acquisition(groups))
    print("\n" + format_search_crawler_coverage(groups))
    print("\n" + format_search_crawler_discovery_activity(groups))
    print("\n" + format_feed_activity(groups))

    print("\n## search/AI crawler user-agents (indexing pipeline signal)")
    bot_total = 0
    bot_rows = {}
    for g in groups:
        ua = (g["dimensions"].get("userAgent") or "").lower()
        if any(b in ua for b in BOT_UAS):
            bot_total += g["count"]
            key = (g["dimensions"]["userAgent"] or "")[:110]
            bot_rows[key] = bot_rows.get(key, 0) + g["count"]
    if bot_rows:
        for ua, c in sorted(bot_rows.items(), key=lambda x: -x[1]):
            print(f"{c:>6}  {ua}")
        print(f"   --> crawler requests: {bot_total}")
    else:
        print("   none observed in window")


if __name__ == "__main__":
    main()
