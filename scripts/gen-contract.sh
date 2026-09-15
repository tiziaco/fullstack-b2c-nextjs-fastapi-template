#!/usr/bin/env bash
# Regenerate the committed contract artifacts from the code that produces them.
#
# server/openapi.json is exported from the FastAPI app, and everything under
# web-app/packages/api-client/src/generated is then produced from that file by
# orval. Both are committed, so this is the command that makes them current
# after a route or schema change.
#
# Always succeeds when the generators succeed, whether or not anything moved —
# it is a generator, not a guard. scripts/check-contract.sh calls it and then
# fails on drift; that is the one CI runs.
#
# Needs no database, no .env and no secrets: app.openapi() builds the schema
# from registered routes. It does need the server's import graph to be intact,
# since exporting the spec imports app.main.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Exporting the OpenAPI spec"
make -C server export-openapi

echo "==> Regenerating the API client"
pnpm --dir web-app --filter @app/api-client gen:api
