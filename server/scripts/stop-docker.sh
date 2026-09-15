#!/bin/bash
set -e

# Script to stop and remove the server container.
#
# Scoped to the server service on purpose: `make docker-stop ENV=<env>` runs a
# full `compose down`, which also takes the database with it.

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

echo "Stopping $SERVICE for the $ENV environment"

# Both are no-ops when nothing is running, so there is nothing to probe for.
compose stop "$SERVICE"
compose rm -f "$SERVICE"

echo "$SERVICE stopped and removed successfully"
