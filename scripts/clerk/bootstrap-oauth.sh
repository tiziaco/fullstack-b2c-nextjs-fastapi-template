#!/usr/bin/env bash
# Create the OAuth application behind Swagger's Authorize button, and write the
# three values it produces into server/.env.<env>.
#
# This is docs/setup/clerk.md §5 — the dashboard visit that creates a public
# (PKCE) client and the copying of its client id, authorize URL and token URL
# into three env vars.
#
# Separate from bootstrap-env.sh on purpose, for two reasons:
#
#   1. The Authorize button is optional. Nothing but /docs reads these values,
#      and the server starts happily without them (they default to "" in
#      app/core/config.py, and the OAuth2 scheme is built with auto_error=False).
#   2. bootstrap-env.sh refuses to run once CLERK_APP_ID is set, because it
#      creates a NEW application. Folding this in would make it unreachable on
#      every instance that has already been bootstrapped — which is all of them
#      after the first run.
#
# An OAuth application is a different Clerk resource from the application itself,
# which is why `clerk env pull` never returned these: it returns the instance's
# publishable and secret keys, and an OAuth client is not part of that.
#
# There is no first-class `clerk oauth-applications` subcommand, so this goes
# through `clerk api` — still the CLI, and still resolving credentials from
# --app/--instance rather than reading a secret key out of the environment. The
# same call seed-users.sh makes.
#
# Idempotent: an application matching $OAUTH_APP_NAME is reused, not duplicated.
# Clerk does not treat the name as unique, so running this twice without the
# lookup would leave two clients and write whichever came back last.
#
# What this does NOT set, same as bootstrap-env.sh: ALLOWED_ORIGINS, and
# CLERK_WEBHOOK_SIGNING_SECRET. The webhook secret genuinely cannot be scripted
# — no API registers an endpoint and returns its whsec_. The OAuth trio can be,
# which is what this script is.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

ENV_NAME="${APP_ENV:-development}"
ENV_FILE="server/.env.$ENV_NAME"
OAUTH_APP_NAME="${CLERK_OAUTH_APP_NAME:-B2C Template Swagger Docs}"

# Must match swagger_ui_oauth2_redirect_url in app/main.py, which FastAPI serves
# at /oauth2-redirect. Clerk rejects the whole authorize request when the
# redirect_uri is not registered verbatim, host and port included.
REDIRECT_URI="${CLERK_OAUTH_REDIRECT_URI:-http://localhost:8100/oauth2-redirect}"

# Must cover the scopes app/api/dependencies/authentication.py declares on
# OAuth2AuthorizationCodeBearer. Clerk's own default is just "profile email", so
# leaving this unset would drop openid and offline_access and Swagger's token
# request would be refused for requesting more than the client is allowed.
SCOPES="${CLERK_OAUTH_SCOPES:-openid profile email offline_access}"

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

echo "==> Verifying the target is a development instance"
require_dev_instance "$CLERK_APP_ID"

api() { clerk api "$@" --app "$CLERK_APP_ID" --instance dev --yes < /dev/null; }

echo "==> 1/3 Looking for an existing \"$OAUTH_APP_NAME\""
# GET returns {data:[...]}; tolerate a bare array too, as seed-users.sh does.
EXISTING="$(api /oauth_applications \
  | jq -c --arg name "$OAUTH_APP_NAME" '
      (if type == "array" then . else (.data // []) end)
      | map(select(.name == $name)) | .[0] // empty
    ')"

if [ -n "$EXISTING" ]; then
  APP_JSON="$EXISTING"
  echo "    reusing $(jq -r '.id' <<< "$APP_JSON")"
else
  echo "==> 2/3 Creating the OAuth application"
  BODY="$(jq -n \
    --arg name "$OAUTH_APP_NAME" \
    --arg uri "$REDIRECT_URI" \
    --arg scopes "$SCOPES" \
    '{
      name: $name,
      public: true,
      pkce_required: true,
      redirect_uris: [$uri],
      scopes: $scopes
    }')"
  APP_JSON="$(api /oauth_applications -X POST -d "$BODY")"
  if [ -z "$(jq -r '.client_id // empty' <<< "$APP_JSON")" ]; then
    echo "FAIL: the API did not return a client_id. Response:"
    jq . <<< "$APP_JSON" 2>/dev/null || echo "$APP_JSON"
    exit 1
  fi
  echo "    created $(jq -r '.id' <<< "$APP_JSON")"
fi

CLIENT_ID="$(jq -r '.client_id' <<< "$APP_JSON")"
AUTHORIZE_URL="$(jq -r '.authorize_url' <<< "$APP_JSON")"
TOKEN_URL="$(jq -r '.token_fetch_url' <<< "$APP_JSON")"

for pair in "client_id:$CLIENT_ID" "authorize_url:$AUTHORIZE_URL" "token_fetch_url:$TOKEN_URL"; do
  if [ -z "${pair#*:}" ] || [ "${pair#*:}" = "null" ]; then
    echo "FAIL: the OAuth application is missing ${pair%%:*}."
    exit 1
  fi
done

echo "==> 3/3 Writing $ENV_FILE"
ensure_env_file "$ENV_FILE" server/.env.example
# server/.env.example quotes its values; match it.
upsert "$ENV_FILE" CLERK_OAUTH_CLIENT_ID "$CLIENT_ID" quoted
upsert "$ENV_FILE" CLERK_AUTHORIZE_URL "$AUTHORIZE_URL" quoted
upsert "$ENV_FILE" CLERK_TOKEN_URL "$TOKEN_URL" quoted

echo
echo "PASS: \"$OAUTH_APP_NAME\" is registered and $ENV_FILE now carries"
echo "      CLERK_OAUTH_CLIENT_ID, CLERK_AUTHORIZE_URL and CLERK_TOKEN_URL."
echo "      Scopes: $SCOPES"
echo "      Redirect URI: $REDIRECT_URI"
echo
echo "Restart the API server for /docs to pick them up."
echo
echo "NOTE: /docs still cannot exercise the admin role. An OAuth access token"
echo "      carries client_id, not the session-token claims, so it never carries"
echo "      the custom 'role' claim and GET /api/v1/admin/ping returns 403 there"
echo "      even for an admin. That is correct — see docs/setup/clerk.md §5."
