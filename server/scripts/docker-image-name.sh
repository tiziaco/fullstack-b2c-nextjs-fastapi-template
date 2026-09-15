#!/usr/bin/env bash
# The one place the server's Docker image name is derived.
#
# PROJECT_NAME names Docker artifacts and nothing else. It is not the API's
# title — that lives in pyproject.toml under [tool.app.metadata], read by
# app/core/metadata.py, and reaches the committed openapi.json. Setting one
# does not change the other, and they are free to differ.
#
# The fallback is not optional: PROJECT_NAME comes from the gitignored
# .env.<env>, so a fresh clone that has not filled one in would otherwise build
# the tag ":<env>" and abort with "invalid reference format".
#
# Callers: Makefile's docker-build and build-docker.sh. Both tag <name>:<env>,
# so they cannot drift apart on what the image is called. Nothing else needs
# this: the Compose stack names its own images and containers, so stop-docker.sh
# and logs-docker.sh address `container_name: server` instead.
#
#     DOCKER_IMAGE_NAME=$(scripts/docker-image-name.sh development)
set -euo pipefail

ENV=${1:?Usage: $0 <environment>}

ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env.$ENV"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# Lowercase, and collapse anything Docker will not accept in a repository name
# into single hyphens.
echo "${PROJECT_NAME:-template-app-server}" |
    tr '[:upper:]' '[:lower:]' |
    sed 's/[^a-z0-9]/-/g' |
    sed 's/--*/-/g' |
    sed 's/^-//' |
    sed 's/-$//'
