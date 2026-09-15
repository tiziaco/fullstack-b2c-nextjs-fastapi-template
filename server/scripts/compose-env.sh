# Sourced by stop-docker.sh and logs-docker.sh — not executable on its own.
#
# Defines compose(), which addresses the stack by *service* name. The container
# name is Compose's to choose: docker-compose.dev.yml pins `server`,
# docker-compose.prod.yml lets it default to <project>-server-1. Naming it in a
# script would be a copy of a value the script does not own, and would be wrong
# for one of the two files. PROJECT_NAME is unrelated — it names the image
# built by build-docker.sh, via docker-image-name.sh.
#
# Expects $ENV to be set and validated by the caller.

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE_FILE="${COMPOSE_FILE:-$SERVER_DIR/../docker-compose.dev.yml}"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker-compose}"
SERVICE="${SERVICE:-server}"
ENV_FILE="$SERVER_DIR/.env.$ENV"

if [ ! -f "$ENV_FILE" ]; then
    echo "Environment file $ENV_FILE not found. Please create it."
    exit 1
fi

# Compose interpolates every service in the file before it selects the one
# asked for, and the root file's grafana and portal services need variables from
# the root .env and the portal's .env.local. --env-file points at
# server/.env.$ENV *instead of* the root .env, not in addition to it, so load
# those here as well — the shell environment outranks --env-file. Same reasoning
# as the Makefile's -include lines, and harmless when make already exported them.
set -a
# shellcheck disable=SC1091
[ -f "$SERVER_DIR/../.env" ] && source "$SERVER_DIR/../.env"
# shellcheck disable=SC1091
[ -f "$SERVER_DIR/../web-app/apps/web/.env.local" ] &&
    source "$SERVER_DIR/../web-app/apps/web/.env.local"
set +a

compose() {
    # Unquoted so DOCKER_COMPOSE can be the two-word "docker compose" (v2) as
    # well as the v1 binary, which is what the Makefile's variable allows too.
    # shellcheck disable=SC2086
    APP_ENV="$ENV" $DOCKER_COMPOSE -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}
