#!/usr/bin/env python3
"""Mokha Caffè Web Analytics (RUM) baseline via Cloudflare GraphQL.

Prints pageload counts per path/host and external referral hosts for the live
RUM site over a lookback window. The referrer summary excludes bot and same-site
events. It does not query visitor IPs. Read-only. Requires
CLOUDFLARE_API_TOKEN in env.

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
GROUP_LIMIT = 100

QUERY = """query($acct: String!, $since: Time!) {
  viewer { accounts(filter: {accountTag: $acct}) {
    pathGroups: rumPageloadEventsAdaptiveGroups(limit: 100,
        filter: {datetime_geq: $since}) {
      count
      dimensions { siteTag requestHost requestPath }
    }
    referrerGroups: rumPageloadEventsAdaptiveGroups(limit: 100,
        filter: {datetime_geq: $since}) {
      count
      dimensions { siteTag refererHost bot }
    } } } }"""

OWN_HOST = "mokhacaffe.com"


def guard_truncation(name, groups):
    """Stop rather than report potentially truncated GraphQL groups."""
    if len(groups) >= GROUP_LIMIT:
        sys.exit(
            f"{name} returned {len(groups)} rows (limit {GROUP_LIMIT}); "
            "refusing to report potentially truncated analytics"
        )


def external_referrers(groups):
    """Aggregate non-bot, off-site referrers for the live RUM site."""
    referrers = {}
    for group in groups:
        dimensions = group.get("dimensions") or {}
        referrer = (dimensions.get("refererHost") or "").lower().rstrip(".")
        is_bot = dimensions.get("bot") in (1, True, "1", "true")
        if (
            dimensions.get("siteTag") == LIVE_SITE
            and referrer
            and referrer != OWN_HOST
            and not referrer.endswith(f".{OWN_HOST}")
            and not is_bot
        ):
            referrers[referrer] = referrers.get(referrer, 0) + group["count"]
    return referrers


def format_referrers(groups):
    """Format external RUM referrers without path or visitor identifiers."""
    referrers = external_referrers(groups)
    lines = ["## external browser referrers"]
    if referrers:
        for host, count in sorted(referrers.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"{count:>5}  {host}")
    else:
        lines.append("none observed in window")
    lines.append("note: pageload counts are not unique visitors; self traffic may remain.")
    return "\n".join(lines)


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
    account = resp["data"]["viewer"]["accounts"][0]
    path_groups = account["pathGroups"]
    referrer_groups = account["referrerGroups"]
    guard_truncation("pathGroups", path_groups)
    guard_truncation("referrerGroups", referrer_groups)

    print(f"# RUM pageloads, last {args.hours}h (since {since})")
    for g in sorted(path_groups, key=lambda x: -x["count"]):
        d = g.get("dimensions")
        if not isinstance(d, dict):
            continue
        if not args.all_sites and d.get("siteTag") != LIVE_SITE:
            continue
        host = d.get("requestHost") or ""
        path = d.get("requestPath") or ""
        site_tag = d.get("siteTag") or ""
        print(f"{g['count']:>5}  {host}{path}  [{site_tag[:8]}]")
    live_total = sum(
        g["count"]
        for g in path_groups
        if (g.get("dimensions") or {}).get("siteTag") == LIVE_SITE
    )
    print(f"total (live site): {live_total}")
    print("note: self/verification visits are included; label them when recording baselines.")
    print("\n" + format_referrers(referrer_groups))


if __name__ == "__main__":
    main()
