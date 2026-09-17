#!/usr/bin/env bash
# Create a Clerk application and fill in the Clerk values across all three env files.
#
# This replaces steps 1 and 3 of docs/setup/clerk.md — the dashboard visit that
# produces a publishable key, a secret key and an issuer URL, and the copying of
# each into a different file. It does NOT configure the instance; run
# 'make clerk-apply-config' after this.
#
# `clerk env pull` alone is not enough, for two reasons:
#
#   1. It writes only the publishable and secret keys. CLERK_ISSUER — the trust
#      anchor the server derives its JWKS URL from — is not among them. We derive
#      it instead: a publishable key is base64 of the frontend-API host.
#   2. It targets one env file, and this repo has three, each wanting a different
#      subset under different names.
#
# So we pull into a throwaway temp file and do the merge ourselves, key by key.
# That also sidesteps an unknown: whether `env pull` merges into an existing file
# or rewrites it. web-app/apps/web/.env.local already holds NEXT_PUBLIC_API_URL
# and the four sign-in/sign-up redirect URLs, and losing those would break the app
# in a way that looks nothing like a Clerk problem.
#
# Two values this deliberately does NOT set, because it cannot:
#   - CLERK_WEBHOOK_SIGNING_SECRET — no API creates a Svix endpoint and returns
#     its whsec_. See docs/setup/clerk-webhooks.md.
#   - ALLOWED_ORIGINS — not a Clerk value at all, but a missing entry rejects
#     valid tokens as token_party_not_allowed. See docs/setup/clerk.md §4.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

APP_NAME="${CLERK_APP_NAME:-B2C Template Dev}"

if ! command -v jq > /dev/null 2>&1; then
  echo "FAIL: jq is not installed."
  echo "Install it with 'brew install jq'."
  exit 1
fi

# Creating a second application by accident is tedious to undo and leaves the
# repo pointing at whichever one was written last.
if [ -n "${CLERK_APP_ID:-}" ]; then
  echo "FAIL: CLERK_APP_ID is already set to $CLERK_APP_ID."
  echo "This target creates a NEW application. If you meant to reconfigure the"
  echo "existing one, run 'make clerk-apply-config' and 'make clerk-seed-users'."
  echo "To start over, remove CLERK_APP_ID from the root .env first."
  exit 1
fi

# A publishable key is base64 of the frontend-API host, with a trailing '$' inside
# the payload. macOS base64 -d emits silent garbage on unpadded input, so pad first.
derive_issuer() { # derive_issuer <publishable key>
  local payload=$1 host
  payload="${payload#pk_test_}"
  payload="${payload#pk_live_}"
  while [ $(( ${#payload} % 4 )) -ne 0 ]; do payload="${payload}="; done
  host="$(printf '%s' "$payload" | base64 -d 2>/dev/null || true)"
  host="${host%\$}"
  if [ -z "$host" ]; then
    echo "FAIL: could not derive the instance host from the publishable key." >&2
    exit 1
  fi
  printf 'https://%s' "$host"
}

TMP="$(mktemp)"
trap 'rm -f "$TMP" "$TMP.tmp"' EXIT

echo "==> 1/4 Creating the Clerk application \"$APP_NAME\""
APP_ID="$(clerk apps create "$APP_NAME" --json | jq -r '.application_id // .id // empty')"
if [ -z "$APP_ID" ]; then
  echo "FAIL: 'clerk apps create' did not return an application id."
  exit 1
fi
echo "    $APP_ID"

echo "==> 2/4 Pulling the development instance keys"
clerk env pull --app "$APP_ID" --instance dev --file "$TMP" > /dev/null

# Read whatever names the CLI chose. It prefixes the publishable key by detected
# framework (NEXT_PUBLIC_, VITE_, PUBLIC_, EXPO_PUBLIC_, or none), and the
# detection runs against the current directory — which is the monorepo root here,
# not the Next.js app. Match on the suffix and write our own canonical names.
PUBLISHABLE_KEY="$(grep -E '^[A-Z_]*CLERK_PUBLISHABLE_KEY=' "$TMP" | head -n 1 | cut -d= -f2- | tr -d '"' || true)"
SECRET_KEY="$(grep -E '^CLERK_SECRET_KEY=' "$TMP" | head -n 1 | cut -d= -f2- | tr -d '"' || true)"

if [ -z "$PUBLISHABLE_KEY" ] || [ -z "$SECRET_KEY" ]; then
  echo "FAIL: 'clerk env pull' did not return both keys."
  echo "It wrote these names:"
  grep -oE '^[A-Z_]+' "$TMP" || true
  exit 1
fi

ISSUER="$(derive_issuer "$PUBLISHABLE_KEY")"
echo "    issuer $ISSUER"

echo "==> 3/4 Writing env files"
ensure_env_file .env .env.example
ensure_env_file web-app/apps/web/.env.local web-app/apps/web/.env.example
ensure_env_file server/.env.development server/.env.example

upsert .env CLERK_APP_ID "$APP_ID"
upsert web-app/apps/web/.env.local NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY "$PUBLISHABLE_KEY"
upsert web-app/apps/web/.env.local CLERK_SECRET_KEY "$SECRET_KEY"
# server/.env.example quotes its values; match it.
upsert server/.env.development CLERK_SECRET_KEY "$SECRET_KEY" quoted
upsert server/.env.development CLERK_ISSUER "$ISSUER" quoted

echo "==> 4/4 Done"
echo
echo "PASS: application \"$APP_NAME\" created and its keys written to"
echo "      .env, web-app/apps/web/.env.local and server/.env.development."
echo
echo "Next:"
echo "  make clerk-apply-config    configure the instance (role claim, password sign-in)"
echo "  make clerk-seed-users      create the two dev users"
echo
echo "NOTE: two values are not set by this script."
echo "  ALLOWED_ORIGINS in server/.env.development must list the web app's"
echo "    origin, or valid tokens are refused as token_party_not_allowed."
echo "  CLERK_WEBHOOK_SIGNING_SECRET has no API and must come from the Clerk"
echo "    dashboard — see docs/setup/clerk-webhooks.md."
