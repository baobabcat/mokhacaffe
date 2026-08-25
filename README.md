# mokhacaffe.com

Mokha Caffè — founding-stage specialty coffee brand site. Static assets on
Cloudflare Workers Static Assets, served by a tiny Worker that 301s www → apex.

## Layout
- `public/` — the site (zero build step: HTML/CSS/SVG, self-hosted Fraunces)
- `src/index.js` — Worker: www→apex 301, then serves `public/` via ASSETS
- `wrangler.jsonc` — name, routes (custom domains apex + www), assets binding
- `tools/gen_og.py` — regenerates `public/assets/og.png` (pure stdlib)

## Deploy
    CLOUDFLARE_API_TOKEN=... wrangler deploy

Rules: git + wrangler only, no console hand-edits. Factual integrity: no
invented business, inventory, testimonials, prices, or revenue. See
~/.hermes/plans/2026-08-24_222247-mokhacaffe-relaunch.md (incl. §9 directive).
