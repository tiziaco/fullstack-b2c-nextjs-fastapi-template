#!/usr/bin/env bash
# Verify the committed contract artifacts match the code that produces them.
#
# server/openapi.json and web-app/packages/api-client/src/generated/ are both
# generated and committed. If a route changes and only one of them is
# regenerated, the frontend compiles against a contract the backend no longer
# serves — and nothing fails until runtime. This regenerates both and fails if
# anything moved.
#
# Regeneration itself lives in gen-contract.sh so the two commands cannot drift
# apart: this script is that one plus a diff.
#
# Needs no database, no .env and no secrets: app.openapi() builds the schema
# from registered routes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

ARTIFACTS=(server/openapi.json web-app/packages/api-client/src/generated)

"$SCRIPT_DIR/gen-contract.sh"

echo "==> Checking for drift"
# --porcelain covers both modified tracked files and new untracked ones; a plain
# `git diff` would miss a newly generated file for a newly added endpoint.
if [ -n "$(git status --porcelain -- "${ARTIFACTS[@]}")" ]; then
  echo
  echo "FAIL: the committed contract artifacts are stale."
  echo "Run 'make gen-contract' locally and commit the result alongside the"
  echo "route change that caused it."
  echo
  git --no-pager status --porcelain -- "${ARTIFACTS[@]}"
  echo
  git --no-pager diff --stat -- "${ARTIFACTS[@]}"
  exit 1
fi

echo "PASS: server/openapi.json and the generated client are up to date."
