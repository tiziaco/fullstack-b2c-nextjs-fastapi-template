#!/usr/bin/env bash
# Refresh the committed Clerk instance baseline from the live development instance.
#
# scripts/clerk/config.json is a *projection*, not a dump. `clerk config pull`
# returns ~50 top-level keys — every OAuth provider, branding, compliance, billing
# — and committing all of that would churn on every Clerk product change while
# burying the handful of settings this template actually depends on. So the
# baseline names only the keys we assert, and this script rewrites their values
# from the instance. Everything else on the instance is left alone, because
# apply-config.sh sends a PATCH, not a replace.
#
# That projection is also what keeps check-config.sh honest: an unrelated change
# in the Clerk dashboard is not drift, because it is not a key we claim.
#
# Two jq subtleties, both load-bearing, both learned the hard way:
#
#   1. The obvious `paths(scalars)` is WRONG. jq's paths(f) filters by
#      truthiness, so every `false` and `null` leaf silently disappears:
#          $ jq -nc '[{"a":false,"b":true,"c":null} | paths(scalars)]'
#          [["b"]]
#      Nearly every assertion in the baseline is a `false` — device_trust,
#      enforce_hibp_on_sign_in, the MFA switches — so that formulation would
#      quietly delete them from the committed file on the first run. We select
#      on type instead, and treat an empty array (sign_in_strategies: []) as a
#      leaf too, since it has no scalar descendants to find.
#
#   2. The API never returns the `session` block — `clerk config pull` reports
#      "session": null even when a session-token customization is configured.
#      Taken literally that would write session.claims.role: null, show as
#      permanent drift, and then apply-config.sh would PATCH the null back and
#      WIPE the role claim. So where the instance reports null we keep the
#      baseline's own value.
#
#      The cost is real and worth stating plainly: drift in session.claims
#      CANNOT be detected by check-config.sh. That one key is write-only. If
#      someone edits the session token customization in the dashboard, only
#      re-running apply-config.sh puts it back.
#
# Usage:
#   pull-config.sh           project the instance onto the committed baseline
#   pull-config.sh --full    dump the untrimmed instance config to stdout
#
# --full is the bootstrap path, for picking new keys to assert before a baseline
# covers them. It writes nothing.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

BASELINE=scripts/clerk/config.json

if ! command -v jq > /dev/null 2>&1; then
  echo "FAIL: jq is not installed."
  echo "Install it with 'brew install jq'."
  exit 1
fi

if [ -z "${CLERK_APP_ID:-}" ]; then
  echo "FAIL: CLERK_APP_ID is not set."
  echo "Add it to the root .env — 'make clerk-bootstrap-env' writes it there"
  echo "after creating the application. See docs/setup/clerk.md."
  exit 1
fi

# Fetch once, into a temp file, so a non-JSON response (an auth failure, a
# rate limit) is reported as itself rather than as a confusing jq parse error.
# The CLI puts its progress chatter on stderr and JSON on stdout.
LIVE="$(mktemp)"
trap 'rm -f "$LIVE"' EXIT

# Progress goes to stderr, not stdout: --full dumps JSON to stdout and is meant
# to be redirected or piped, so anything else written there would corrupt it.
echo "==> Pulling instance config" >&2
clerk config pull --app "$CLERK_APP_ID" --instance dev > "$LIVE"

if ! jq -e . "$LIVE" > /dev/null 2>&1; then
  echo "FAIL: 'clerk config pull' did not return JSON." >&2
  echo "Response was:" >&2
  cat "$LIVE" >&2
  exit 1
fi

if [ "${1:-}" = "--full" ]; then
  jq -S . "$LIVE"
  exit 0
fi

echo "==> Projecting onto $BASELINE" >&2
# -S sorts keys so the committed file has one canonical ordering and diffs
# reflect changed values rather than reshuffled ones.
jq -S -n \
  --slurpfile baseArr "$BASELINE" \
  --slurpfile liveArr "$LIVE" '
  $baseArr[0] as $base
  | $liveArr[0] as $live
  | [ $base
      | paths as $p
      | ($base | getpath($p)) as $v
      | ($v | type) as $t
      | select(($t != "object" and $t != "array") or ($v | length) == 0)
      | $p
    ]
  | reduce .[] as $p ({};
      setpath($p;
        ($live | getpath($p)) as $lv
        | if $lv == null then ($base | getpath($p)) else $lv end))
' > "$BASELINE.tmp"

mv "$BASELINE.tmp" "$BASELINE"
echo "PASS: $BASELINE now reflects the live development instance."
