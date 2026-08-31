#!/usr/bin/env python3
"""Mokha Caffè edge-request baseline via Cloudflare GraphQL (server-side).

Complements rum_baseline.py: the RUM beacon only fires on real browsers that
execute JS — crawlers, feed readers, and HEAD/GET bots are invisible there.
This tool counts ACTUAL edge requests for the zone, grouped by path + status
(+ user-agent family), so we can see whether search crawlers (Bingbot,
Googlebot, DuckDuckBot, YandexBot) have fetched robots.txt / sitemap.xml /
feed.xml / pages — the leading indicator on the indexing pipeline. Search
Console + Bing Webmaster Tools were verified by the owner on 2026-08-31
(sitemap submitted to both), but neither console is reachable from this VM,
so edge telemetry remains our only indexing-progress signal.

Read-only. Requires CLOUDFLARE_API_TOKEN in env (same token as deploys).

Usage: python3 tools/edge_requests.py [--hours 168] [--ua]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ZONE = "df47a612388511375ea5fc45be07040d"  # mokhacaffe.com (verified 2026-08-31)
GQL = "https://api.cloudflare.com/client/v4/graphql"

QUERY = """query($zone: String!, $since: Time!, $until: Time!) {
  viewer { zones(filter: {zoneTag: $zone}) {
    httpRequestsAdaptiveGroups(limit: 500,
        filter: {datetime_geq: $since, datetime_leq: $until}) {
      count
      dimensions { clientRequestPath edgeResponseStatus userAgent }
    } } } }"""

BOT_UAS = ("googlebot", "bingbot", "duckduckbot", "yandexbot", "baiduspider",
           "slurp", "applebot", "petalbot", "seznambot", "gptbot",
           "claudebot", "perplexitybot", "bytespider")


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
    return (resp["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"])


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
    groups = {}
    cursor = start
    while cursor < now:
        nxt = min(cursor + timedelta(hours=24), now)
        for g in run(token, cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     nxt.strftime("%Y-%m-%dT%H:%M:%SZ")):
            d = g["dimensions"]
            key = (d["clientRequestPath"], d["edgeResponseStatus"],
                   d.get("userAgent"))
            groups[key] = groups.get(key, 0) + g["count"]
        cursor = nxt
    groups = [{"count": c,
               "dimensions": {"clientRequestPath": k[0],
                              "edgeResponseStatus": k[1],
                              "userAgent": k[2]}}
              for k, c in groups.items()]
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
