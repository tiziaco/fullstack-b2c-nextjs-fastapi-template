#!/bin/bash
set -e

# Script to view the server container's logs.

if [ $# -ne 1 ]; then
  echo "Usage: $0 <environment>"
  echo "Environments: development, staging, production"
  exit 1
fi

ENV=$1

# Validate environment
if [[ ! "$ENV" =~ ^(development|staging|production)$ ]]; then
  echo "Invalid environment. Must be one of: development, staging, production"
  exit 1
fi

# shellcheck source=compose-env.sh
source "$(dirname "${BASH_SOURCE[0]}")/compose-env.sh"

if [ -z "$(compose ps -q "$SERVICE")" ]; then
  echo "$SERVICE is not running. Start it first with:"
  echo "  make docker-run"
  exit 1
fi

echo "Following logs from $SERVICE (Ctrl+C to exit)"
compose logs -f "$SERVICE"
