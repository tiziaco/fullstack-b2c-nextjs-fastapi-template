#!/bin/bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <environment>"
  echo "Environments: development, staging, production"
  exit 1
fi

ENV=$1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.$ENV"

if [ -f "$ENV_FILE" ]; then
  echo "Loading environment variables from $ENV_FILE for database initialization"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Warning: $ENV_FILE not found. Falling back to current environment for database initialization."
fi

POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
POSTGRES_DB=${POSTGRES_DB:-food_order_db}

DOCKER_COMPOSE_BIN=${DOCKER_COMPOSE_BIN:-docker compose}
IFS=' ' read -r -a DC_CMD <<< "$DOCKER_COMPOSE_BIN"
# PROJECT_ROOT here is server/ (SCRIPT_DIR/..); the root docker-compose.dev.yml
# lives one level up and is not a Compose default filename, so it must be
# passed explicitly.
DC_CMD+=(-f "$PROJECT_ROOT/../docker-compose.dev.yml")

echo "Waiting for PostgreSQL service to be ready..."
MAX_ATTEMPTS=30
SLEEP_SECONDS=2
attempt=1

until "${DC_CMD[@]}" exec -T db pg_isready -U postgres >/dev/null 2>&1; do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "PostgreSQL service did not become ready in time."
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done

echo "Ensuring role '$POSTGRES_USER' and database '$POSTGRES_DB' exist"

# Simple approach - no escaping needed when using double quotes properly
role_exists=$("${DC_CMD[@]}" exec -T db psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$POSTGRES_USER'" | tr -d '[:space:]')
if [ "$role_exists" != "1" ]; then
  echo "Creating role $POSTGRES_USER"
  "${DC_CMD[@]}" exec -T db psql -U postgres -c "CREATE ROLE $POSTGRES_USER WITH LOGIN PASSWORD '$POSTGRES_PASSWORD'"
else
  echo "Updating password for role $POSTGRES_USER"
  "${DC_CMD[@]}" exec -T db psql -U postgres -c "ALTER ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD'"
fi

db_exists=$("${DC_CMD[@]}" exec -T db psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB'" | tr -d '[:space:]')
if [ "$db_exists" != "1" ]; then
  echo "Creating database $POSTGRES_DB owned by $POSTGRES_USER"
  "${DC_CMD[@]}" exec -T db psql -U postgres -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER"
else
  echo "Database $POSTGRES_DB already exists, ensuring owner"
  "${DC_CMD[@]}" exec -T db psql -U postgres -c "ALTER DATABASE $POSTGRES_DB OWNER TO $POSTGRES_USER"
fi

echo "Granting privileges on database $POSTGRES_DB to $POSTGRES_USER"
"${DC_CMD[@]}" exec -T db psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER"

echo "PostgreSQL role and database ensured successfully"

