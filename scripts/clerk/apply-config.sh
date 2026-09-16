#!/usr/bin/env bash
# Apply the committed Clerk instance baseline to the live development instance.
#
# This is step 2 of docs/setup/clerk.md as code: it is what puts the `role`
# claim on every session token, and what turns on email+password sign-in with
# the policy relaxations a seeded fake user needs in order to sign in at all.
#
# It sends a PATCH, so it asserts only the keys named in config.json and leaves
# every other instance setting alone. --destructive is deliberately NOT passed:
# that flag lets a patch delete resources (session templates, custom OAuth
# providers) rather than reset them to defaults, and nothing this template
# asserts needs it. Preview any change with --dry-run before applying.
#
# Safe to re-run: applying an already-applied baseline is a no-op.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

BASELINE=scripts/clerk/config.json

if [ -z "${CLERK_APP_ID:-}" ]; then
  echo "FAIL: CLERK_APP_ID is not set."
  echo "Add it to the root .env — 'make clerk-bootstrap-env' writes it there"
  echo "after creating the application. See docs/setup/clerk.md."
  exit 1
fi

if [ ! -f "$BASELINE" ]; then
  echo "FAIL: $BASELINE not found."
  echo "It is committed to the repo; restore it with 'git checkout -- $BASELINE'."
  exit 1
fi

echo "==> Applying $BASELINE to the development instance"
clerk config patch --app "$CLERK_APP_ID" --instance dev --file "$BASELINE" --yes "$@"

echo "PASS: instance config matches the committed baseline."
echo
echo "NOTE: this does not seed users or set ALLOWED_ORIGINS. Run"
echo "      'make clerk-seed-users' next, and check that ALLOWED_ORIGINS in"
echo "      server/.env.development lists the web app's origin — a missing"
echo "      entry rejects valid tokens as token_party_not_allowed."
