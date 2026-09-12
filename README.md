# mokhacaffe.com

Mokha Caffè — founding-stage specialty coffee brand site. Static assets on
Cloudflare Workers Static Assets, served by a tiny Worker that 301s www → apex.

## Layout
- `public/` — the site (zero build step: HTML/CSS/SVG, self-hosted Fraunces)
- `src/index.js` — Worker: www→apex 301, then serves `public/` via ASSETS
- `wrangler.jsonc` — name, routes (custom domains apex + www), assets binding
- `tools/gen_og.py` — regenerates `public/assets/og.png` (pure stdlib)
- `tools/seo_audit.py` — on-page/sitemap/feed/link audit of the live site
- `/coffee-ratio-calculator/` — browser-only coffee-to-water calculator linked
  from the Better Coffee at Home guide. It sends a `ratio_calculation` GA4 event
  on form submission with only the calculation direction, never entered amounts.
- `tools/rum_baseline.py` — Web Analytics pageload and external-referrer baseline
  via separate GraphQL grouping aliases (browser-only, excludes bot and every
  mokhacaffe.com subdomain from its referrer summary; aborts rather than report
  potentially truncated groups; never queries visitor IPs)
- Google Analytics 4 measurement `G-HJNKHJZZLL` is installed on every HTML page.
  The CSP permits only the required Google tag and analytics origins and
  authorizes the inline initializer by SHA-256 rather than `'unsafe-inline'`.
  The contact page records a `contact_intent` event with `contact_method=email`
  when a visitor opens the official email link. This measures intent, not a sent
  message or a qualified lead.
- `tools/edge_requests.py` — server-side edge-request baseline via GraphQL
  (successful canonical-page requests plus crawler visibility the RUM beacon
  cannot see; canonical requests are split between known crawler signatures and
  all other user agents; the report compares search-crawler requests for
  robots.txt, sitemap.xml, feed.xml, and canonical content, and the main search
  crawlers show canonical-path coverage for the lookback window. It also splits
  successful feed requests among named feed-reader signatures, site checks,
  crawlers, browsers, and unidentified clients. User-agent signatures are not
  treated as verified identities, and requests are not treated as subscriptions
  or distinct readers; Free-plan windows are capped at one day, then sliced and
  merged)
- `tools/indexnow_ping.py` — submits sitemap URLs to IndexNow (Bing/Yandex)
- `tools/bing_webmaster.py` — Bing Webmaster API client (URL submission via
  SubmitUrlBatch + verifiable index/crawl/query stats). Reads the configured
  `BING_WEBMASTER_API_KEY` environment variable; the key is never committed.
- `tools/gen_feed.py` — regenerates `public/feed.xml` (Atom) from the journal index;
  the feed is linked in every page footer so readers can follow new guides without
  giving Mokha an email address. Opening a visible Feed link records a `feed_open`
  GA4 event with no custom event details, entered values, or message content.

## Deploy
    CLOUDFLARE_API_TOKEN=... wrangler deploy

After any deploy that adds/changes URLs (new journal post, new page):
1. bump `lastmod` in `public/sitemap.xml`,
2. for journal changes, `python3 tools/gen_feed.py` (regenerates `feed.xml`),
3. `wrangler deploy`,
4. `python3 tools/indexnow_ping.py` (key file lives at
   `public/79ab30351487365090c7d6b534c3dbb4.txt`; HTTP 200/202 = accepted).

Rules: git + wrangler only, no console hand-edits. Factual integrity: no
invented business, inventory, testimonials, prices, or revenue. See
~/.hermes/plans/2026-08-24_222247-mokhacaffe-relaunch.md (incl. §9 directive).

## Disclosure
This repository is maintained by an autonomous AI agent (Hermes, running as
github.com/baobabcat) under its owner's direction. The brand itself is
founding-stage and human-owned; the agent builds, deploys, and audits the
site and writes the journal content. No part of this repo implies an
operating café, catalog, or sales operation — there is none yet.
