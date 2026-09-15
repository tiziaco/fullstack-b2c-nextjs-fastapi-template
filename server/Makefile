install:
	pip install uv
	uv sync

DOCKER_COMPOSE ?= docker-compose
# Root compose file lives one level up; docker-compose.dev.yml is not a
# Compose *default* filename, so it will not be found by implicit lookup.
COMPOSE_FILE ?= ../docker-compose.dev.yml

# That compose file is the whole stack, and Compose interpolates every service
# in it before it selects the one or two asked for below. grafana and the two
# portals require variables that live in the root .env and the portal's
# .env.local, and the --env-file flag on the targets below points at
# server/.env.<env> *instead of* the root .env, not in addition to it. Load them
# here, as the root Makefile does: the shell environment outranks --env-file, so
# exported values win. Without this, `docker-run` dies on
# "GRAFANA_ADMIN_PASSWORD is required" without ever reaching db or server.
-include ../.env
-include ../web-app/apps/web/.env.local
.EXPORT_ALL_VARIABLES:

# Host port for the native (non-Docker) server. 8000 collides with other
# projects on the same machine; keep this in step with API_HOST_PORT in the
# root Makefile, which publishes the same port from the container.
PORT ?= 8100

set-env:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make set-env ENV=development|staging|production"; \
		exit 1; \
	fi
	@if [ "$(ENV)" != "development" ] && [ "$(ENV)" != "staging" ] && [ "$(ENV)" != "production" ] && [ "$(ENV)" != "test" ]; then \
		echo "ENV is not valid. Must be one of: development, staging, production, test"; \
		exit 1; \
	fi
	@echo "Setting environment to $(ENV)"
	@bash -c "source scripts/set_env.sh $(ENV)"

prod:
	@echo "Starting server in production environment"
	@bash -c "source scripts/set_env.sh production && ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --loop uvloop"

staging:
	@echo "Starting server in staging environment"
	@bash -c "source scripts/set_env.sh staging && ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --loop uvloop"

dev:
	@echo "Starting server in development environment"
	@bash -c "source scripts/set_env.sh development && uv run uvicorn app.main:app --reload --host localhost --port $(PORT) --loop uvloop"

# Evaluation commands
eval:
	@echo "Running evaluation with interactive mode"
	@bash -c "source scripts/set_env.sh ${ENV:-development} && python -m evals.main --interactive"

eval-quick:
	@echo "Running evaluation with default settings"
	@bash -c "source scripts/set_env.sh ${ENV:-development} && python -m evals.main --quick"

eval-no-report:
	@echo "Running evaluation without generating report"
	@bash -c "source scripts/set_env.sh ${ENV:-development} && python -m evals.main --no-report"

# Testing commands
# APP_ENV=test is enough — pydantic-settings auto-loads .env.test
test:
	@echo "Running all tests"
	@APP_ENV=test uv run pytest tests/ -v

test-unit:
	@echo "Running unit tests"
	@APP_ENV=test uv run pytest tests/unit/ -v -m unit

test-integration:
	@echo "Running integration tests"
	@APP_ENV=test uv run pytest tests/integration/ -v -m integration

test-coverage:
	@echo "Running all tests with coverage report"
	@APP_ENV=test uv run pytest tests/ -v \
		--cov=app \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml

test-fast:
	@echo "Running all tests except slow ones"
	@APP_ENV=test uv run pytest tests/ -v -m "not slow"

lint:
	ruff check .

format:
	ruff format .

# The OpenAPI spec is a committed artifact: it generates the frontend client.
# Needs no database, no network and no secrets — app.openapi() builds the schema
# from registered routes.
export-openapi:
	@echo "Exporting OpenAPI spec to server/openapi.json"
	@APP_ENV=$${APP_ENV:-development} PYTHONPATH=. uv run python scripts/export_openapi.py

clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache

# Fast cached build of the development image. docker-build-env does the same
# through scripts/build-docker.sh, which forces --no-cache and passes the secret
# build args; use that one for staging and production. Both take the tag from
# scripts/docker-image-name.sh, so they cannot disagree on <name>:<env>.
#
# The docker-run/logs/stop targets below do not use this image name at all —
# Compose builds and names their containers itself.
docker-build:
	@DOCKER_IMAGE=$$(./scripts/docker-image-name.sh development) && \
		docker build -t "$$DOCKER_IMAGE:development" .

docker-build-env:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-build-env ENV=development|staging|production"; \
		exit 1; \
	fi
	@if [ "$(ENV)" != "development" ] && [ "$(ENV)" != "staging" ] && [ "$(ENV)" != "production" ]; then \
		echo "ENV is not valid. Must be one of: development, staging, production"; \
		exit 1; \
	fi
	@./scripts/build-docker.sh $(ENV)

# Development only, and deliberately not parameterised by ENV. COMPOSE_FILE is
# the dev compose file, which bind-mounts ./server/app over the image's code, so
# an `ENV=production` variant would pair production secrets with your working
# tree — dev topology, prod config. Production runs from
# docker-compose.prod.yml, which these targets never touch.
docker-run:
	@ENV_FILE=.env.development; \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Environment file $$ENV_FILE not found. Please create it."; \
		exit 1; \
	fi; \
	APP_ENV=development $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --env-file $$ENV_FILE up -d --build db server

docker-logs:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-logs ENV=development|staging|production"; \
		exit 1; \
	fi
	@if [ "$(ENV)" != "development" ] && [ "$(ENV)" != "staging" ] && [ "$(ENV)" != "production" ]; then \
		echo "ENV is not valid. Must be one of: development, staging, production"; \
		exit 1; \
	fi
	@ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Environment file $$ENV_FILE not found. Please create it."; \
		exit 1; \
	fi; \
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --env-file $$ENV_FILE logs -f server db

docker-stop:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-stop ENV=development|staging|production"; \
		exit 1; \
	fi
	@if [ "$(ENV)" != "development" ] && [ "$(ENV)" != "staging" ] && [ "$(ENV)" != "production" ]; then \
		echo "ENV is not valid. Must be one of: development, staging, production"; \
		exit 1; \
	fi
	@ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Environment file $$ENV_FILE not found. Please create it."; \
		exit 1; \
	fi; \
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --env-file $$ENV_FILE down

# Server-scoped counterparts to docker-logs and docker-stop above, which act on
# the whole stack (docker-stop takes the database down with it). They delegate,
# so each behaviour has one implementation: the target checks that ENV was
# passed, the script validates its value and talks to Compose.
docker-logs-server:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-logs-server ENV=development|staging|production"; \
		exit 1; \
	fi
	@./scripts/logs-docker.sh $(ENV)

docker-stop-server:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-stop-server ENV=development|staging|production"; \
		exit 1; \
	fi
	@./scripts/stop-docker.sh $(ENV)

docker-run-db:
	@if [ -z "$(ENV)" ]; then \
		echo "ENV is not set. Usage: make docker-run-db ENV=development|staging|production"; \
		exit 1; \
	fi
	@if [ "$(ENV)" != "development" ] && [ "$(ENV)" != "staging" ] && [ "$(ENV)" != "production" ]; then \
		echo "ENV is not valid. Must be one of: development, staging, production"; \
		exit 1; \
	fi
	@ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Environment file $$ENV_FILE not found. Please create it."; \
		exit 1; \
	fi; \
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --env-file $$ENV_FILE up -d db

# Migrations
migrate:
	@if [ -z "$(ENV)" ]; then \
		echo "Error: ENV is required. Usage: make migrate ENV=<environment>"; \
		exit 1; \
	fi; \
	ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Error: Environment file $$ENV_FILE not found"; \
		exit 1; \
	fi; \
	echo "Running migrations for $(ENV) environment..."; \
	set -a && . ./$$ENV_FILE && set +a && \
	APP_ENV=$(ENV) uv run alembic upgrade head

migrate-create:
	@if [ -z "$(ENV)" ]; then \
		echo "Error: ENV is required. Usage: make migrate-create ENV=<environment> MSG='migration message'"; \
		exit 1; \
	fi; \
	if [ -z "$(MSG)" ]; then \
		echo "Error: MSG is required. Usage: make migrate-create ENV=<environment> MSG='migration message'"; \
		exit 1; \
	fi; \
	ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Error: Environment file $$ENV_FILE not found"; \
		exit 1; \
	fi; \
	echo "Creating migration for $(ENV) environment..."; \
	set -a && . ./$$ENV_FILE && set +a && \
	APP_ENV=$(ENV) uv run alembic revision --autogenerate -m "$(MSG)"

migrate-downgrade:
	@if [ -z "$(ENV)" ]; then \
		echo "Error: ENV is required. Usage: make migrate-downgrade ENV=<environment> [REV=-1]"; \
		exit 1; \
	fi; \
	ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Error: Environment file $$ENV_FILE not found"; \
		exit 1; \
	fi; \
	REV=$${REV:--1}; \
	echo "Downgrading migrations for $(ENV) environment to $$REV..."; \
	set -a && . ./$$ENV_FILE && set +a && \
	APP_ENV=$(ENV) uv run alembic downgrade $$REV

migrate-history:
	@if [ -z "$(ENV)" ]; then \
		echo "Error: ENV is required. Usage: make migrate-history ENV=<environment>"; \
		exit 1; \
	fi; \
	ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Error: Environment file $$ENV_FILE not found"; \
		exit 1; \
	fi; \
	echo "Migration history for $(ENV) environment:"; \
	set -a && . ./$$ENV_FILE && set +a && \
	APP_ENV=$(ENV) uv run alembic history --verbose

migrate-current:
	@if [ -z "$(ENV)" ]; then \
		echo "Error: ENV is required. Usage: make migrate-current ENV=<environment>"; \
		exit 1; \
	fi; \
	ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then \
		echo "Error: Environment file $$ENV_FILE not found"; \
		exit 1; \
	fi; \
	echo "Current migration for $(ENV) environment:"; \
	set -a && . ./$$ENV_FILE && set +a && \
	APP_ENV=$(ENV) uv run alembic current

# Help
help:
	@echo "Usage: make <target>"
	@echo "Targets:"
	@echo "  install: Install dependencies"
	@echo "  set-env ENV=<environment>: Set environment variables (development, staging, production, test)"
	@echo "  run ENV=<environment>: Set environment and run server"
	@echo "  prod: Run server in production environment"
	@echo "  staging: Run server in staging environment"
	@echo "  dev: Run server in development environment"
	@echo "  eval: Run evaluation with interactive mode"
	@echo "  eval-quick: Run evaluation with default settings"
	@echo "  eval-no-report: Run evaluation without generating report"
	@echo "  test: Run all tests"
	@echo "  test-unit: Run unit tests only"
	@echo "  test-integration: Run integration tests only"
	@echo "  test-coverage: Run all tests with HTML + XML coverage report"
	@echo "  test-fast: Run all tests except slow ones"
	@echo "  clean: Clean up"
	@echo "  docker-build: Build default Docker image"
	@echo "  docker-build-env ENV=<environment>: Build Docker image for specific environment"
	@echo "  docker-run: Start the development stack (server + db)"
	@echo "  docker-run-db ENV=<environment>: Start the database only"
	@echo "  docker-logs ENV=<environment>: Follow logs from the server and db containers"
	@echo "  docker-stop ENV=<environment>: Stop the whole stack, database included"
	@echo "  docker-logs-server ENV=<environment>: Follow logs from the server container only"
	@echo "  docker-stop-server ENV=<environment>: Stop and remove the server container only"
	@echo "  migrate ENV=<environment>: Run database migrations"
	@echo "  migrate-create ENV=<environment> MSG='message': Create new migration"
	@echo "  migrate-downgrade ENV=<environment> [REV=-1]: Downgrade migrations"
	@echo "  migrate-history ENV=<environment>: Show migration history"
	@echo "  migrate-current ENV=<environment>: Show current migration version"
	@echo "  export-openapi: Export the OpenAPI spec to server/openapi.json"