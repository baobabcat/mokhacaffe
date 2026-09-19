#!/usr/bin/env bash
# Run Mokha's complete non-mutating release gate from one documented entrypoint.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

run() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

run "Python tests" python3 -m unittest discover -s tests -p 'test_*.py'
run "Browser analytics behavior" node --test tests/feed-analytics.test.mjs
run "Python compilation" python3 -m compileall -q tools tests
run "Atom feed synchronization" python3 tools/gen_feed.py --check
run "Working-tree whitespace" git diff --check
run "Staged whitespace" git diff --cached --check
run "Production SEO audit" python3 tools/seo_audit.py
run "Editorial source audit" python3 tools/check_sources.py
run "Cloudflare deployment dry run" npx --no-install wrangler deploy --dry-run
run "Production health matrix" operations/mokhacaffe-health.sh

printf '\nMokha release verification passed. No deployment was performed.\n'
