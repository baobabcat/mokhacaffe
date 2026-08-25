#!/usr/bin/env python3
"""Mokha Caffè Web Analytics (RUM) baseline via Cloudflare GraphQL.

Prints pageload counts per path/host for the live RUM site over a lookback
window. Read-only. Requires CLOUDFLARE_API_TOKEN in env.

Verified 2026-08-25: live site_tag = f43ed716bfde47949c61dbbb55a478ab
(beacon token ad511722c9b244fd8123666ecedafb00 deployed on all pages;
end-to-end verified with two real browser visits appearing within ~5 min).
Note: GraphQL siteTag is the internal site id, NOT the JS beacon token.

Usage: python3 tools/rum_baseline.py [--hours 24] [--all-sites]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ACCT = "76adb356ff1550c08ef68729faf5f03e"
LIVE_SITE = "f43ed716bfde47949c61dbbb55a478ab"
GQL = "https://api.cloudflare.com/client/v4/graphql"

QUERY = """query($acct: String!, $since: Time!) {
  viewer { accounts(filter: {accountTag: $acct}) {
    rumPageloadEventsAdaptiveGroups(limit: 100,
        filter: {datetime_geq: $since}) {
      count
      dimensions { siteTag requestHost requestPath }
    } } } }"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--all-sites", action="store_true",
                    help="include historical/stray site tags")
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("CLOUDFLARE_API_TOKEN not set")
    since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)
             ).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = json.dumps({"query": QUERY,
                       "variables": {"acct": ACCT, "since": since}}).encode()
    req = urllib.request.Request(GQL, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if resp.get("errors"):
        sys.exit(f"GraphQL errors: {resp['errors']}")
    groups = (resp["data"]["viewer"]["accounts"][0]
              ["rumPageloadEventsAdaptiveGroups"])

    total = 0
    print(f"# RUM pageloads, last {args.hours}h (since {since})")
    for g in sorted(groups, key=lambda x: -x["count"]):
        d = g["dimensions"]
        if not args.all_sites and d["siteTag"] != LIVE_SITE:
            continue
        total += g["count"]
        print(f"{g['count']:>5}  {d['requestHost']}{d['requestPath']}"
              f"  [{d['siteTag'][:8]}]")
    print(f"total (live site): {sum(g['count'] for g in groups if g['dimensions']['siteTag'] == LIVE_SITE)}")
    print("note: self/verification visits are included; label them when recording baselines.")


if __name__ == "__main__":
    main()
