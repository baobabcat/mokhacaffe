#!/usr/bin/env bash
# Read-only production health matrix for mokhacaffe.com.
# Silent on success; prints failures and exits 1 otherwise.
set -u

REPO="/home/ubuntu/mokhacaffe"
UA="MokhaVerification/1.0 (read-only; contact hello@mokhacaffe.com)"
FAILS=""

if ! (cd "$REPO" && python3 tools/health_check.py); then
  FAILS="${FAILS}\nFAIL sitemap-derived HTTPS health matrix"
fi

check_redirect() { # url label
  local code target
  read -r code target < <(
    curl -A "$UA" -sS -m 15 -o /dev/null -w '%{http_code} %{redirect_url}' \
      "$1" 2>/dev/null
  )
  if [ "$code" != "301" ] || [ "$target" != "https://mokhacaffe.com/" ]; then
    FAILS="${FAILS}\nFAIL $2: got '${code:-curl-error}' to '${target:-no-location}', expected 301 to https://mokhacaffe.com/"
  fi
}

check_redirect "http://mokhacaffe.com/" "http-to-https"
check_redirect "https://www.mokhacaffe.com/" "www-redirect"

if [ -n "$FAILS" ]; then
  printf 'mokhacaffe.com health check FAILED (%s)\n' "$(date -u '+%Y-%m-%d %H:%M UTC')"
  printf '%b\n' "$FAILS"
  exit 1
fi

exit 0
