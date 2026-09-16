# Template App

A production-ready template for **B2C applications** — one Next.js frontend backed by a
single FastAPI server.

## Overview

The starting point this gives you is the part that is tedious to build and easy to get
wrong: Clerk-backed authentication with a role claim gating the API, an API contract
that cannot silently drift from its client, and a deploy story.

- **Clerk authentication with a platform role** — `user` or `admin`, sourced from
  `publicMetadata.role` and carried on the session token as a custom `role` claim; no
  Organizations, no tenant scoping
- **A Next.js 16 app** built on `packages/core`, `packages/ui`, `packages/components`,
  `packages/auth` and a generated API client
- **A generated, committed API contract** — `server/openapi.json` and the TanStack Query
  hooks derived from it, with four gates that fail if they drift from the routes
- **GDPR erasure** wired end to end, including LangGraph checkpoints and mem0 memories
- **A LangGraph agent** with Langfuse tracing and Postgres checkpointing
- **Observability and deploy** — Prometheus, Grafana, cAdvisor, and a Traefik/Dokploy
  compose file that serves both staging and production

### No example domain

The template ships no worked example — no domain model, no seeded routes beyond
`GET /api/v1/admin/ping`, which exists purely to prove the role guard end to end (see
`server/app/api/dependencies/authorization.py`). Build your domain on top of the auth,
contract and deploy machinery; none of it depends on any example that would need
ripping out first.

---

## Tech Stack

### Frontend (`web-app/`)

| Layer | Technology |
|---|---|
| Framework | [Next.js 16](https://nextjs.org/) + React 19 |
| Language | TypeScript 5 |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui + Base UI + Lucide React |
| Auth | [Clerk](https://clerk.com/) (`@clerk/nextjs`) |
| Data Fetching | TanStack Query v5 |
| Validation | Zod v4 |
| Notifications | Sonner |

### Backend (`server/`)

| Layer | Technology |
|---|---|
| Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Language | Python 3.13+ |
| Runtime | Uvicorn + uvloop |
| ORM / Models | SQLModel + Pydantic v2 |
| Database | PostgreSQL 16 with pgvector |
| Migrations | Alembic |
| Auth | Clerk (JWT via PyJWT + clerk-backend-api) |
| AI / Agents | LangGraph + LangChain + LangChain-OpenAI |
| Memory | Mem0 |
| Observability | Langfuse, Prometheus, structlog |
| Rate Limiting | SlowAPI |
| Package Manager | [uv](https://docs.astral.sh/uv/) |

### Infrastructure

| Component | Technology |
|---|---|
| Database | pgvector/pgvector:pg16 |
| Monitoring | Prometheus + Grafana + cAdvisor |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
.
├── server/                        # FastAPI backend (Python 3.13, uv)
│   ├── app/                       # Application source
│   ├── alembic/                   # Migrations
│   ├── tests/                     # Unit and integration tests
│   ├── openapi.json               # Committed API contract — generated
│   └── pyproject.toml             # Deps AND the service's public identity
├── web-app/                       # Next.js monorepo (pnpm workspaces)
│   ├── apps/
│   │   └── web/                    # The application (port 3000)
│   └── packages/
│       ├── api-client/            # @app/api-client — generated from openapi.json
│       ├── auth/                  # @app/auth — Role, useAppAuth(), getUserRole()
│       ├── core/                  # @app/core — cn(), NavItem, copy; no renderer
│       ├── ui/                    # @app/ui — shadcn/Base UI primitives (web only)
│       └── components/            # @app/components — composed app chrome
├── docs/                          # Setup guides, deploy notes
├── infra/                         # Prometheus + Grafana config
├── scripts/                       # gen-contract, check-contract, verify-infra, deploy-check
├── docker-compose.dev.yml         # Development stack
└── docker-compose.prod.yml        # Staging AND production (switched by APP_ENV)
```

---

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [Node.js](https://nodejs.org/) 20+ and [pnpm](https://pnpm.io/) (for local frontend dev) — this is a pnpm workspace; npm and yarn will not resolve the `@app/*` packages
- [uv](https://docs.astral.sh/uv/) (for local backend dev)
- A [Clerk](https://clerk.com/) application — see [`docs/setup/clerk.md`](docs/setup/clerk.md)

### Environment Files

Copy the example env files and fill in your values:

```bash
# Root (required by the Makefile — provides APP_ENV, GRAFANA_ADMIN_PASSWORD, etc.)
cp .env.example .env

# Backend
cp server/.env.example server/.env.development

# Frontend
cp web-app/apps/web/.env.example web-app/apps/web/.env.local
```

Required variables include Clerk API keys, database credentials, and OpenAI/Langfuse keys.

### Clerk

Nothing authenticates until the Clerk dashboard is configured: `publicMetadata.role` set
to `user`/`admin` on your users, the session token customized to carry it as a `role`
claim, and the web app's origin listed in `ALLOWED_ORIGINS`. Miss the last one and valid
tokens are rejected — it looks like broken auth, not a config error.

Full procedure: [`docs/setup/clerk.md`](docs/setup/clerk.md).

### Git hooks (once per clone)

```bash
git config core.hooksPath .githooks
```

Without this the pre-commit contract gate does not exist, and a route change committed
without its regenerated client is caught only by CI.

### Service Identity (renaming a fork)

The API's title, description and versioned path prefix are **not** environment
variables. They live in `server/pyproject.toml`, and the version alongside them
in `[project]`:

```toml
[project]
version = "0.1.0"

[tool.app.metadata]
title = "B2C Template - Server"
description = "A production-ready FastAPI service with LangGraph and Clerk authentication"
api_v1_str = "/api/v1"
```

Change them there, then regenerate the committed contract and commit the result:

```bash
make gen-contract
```

They are kept out of `.env` on purpose. All four land in the committed
`server/openapi.json` — the first three verbatim in its `info` block,
`api_v1_str` as the prefix on every versioned path — and orval stamps the title
into the header of every generated API client file. Read from a gitignored
`.env.<env>` they would differ per machine, so `make check-contract` would fail
on CI and on every fresh clone the moment anyone set one.

`PROJECT_NAME` in `server/.env.example` is a different thing despite the name:
it only tags the Docker image built by `make -C server docker-build`, and has no
effect on the API's title.

---

## Running the Application

### Full Stack with Docker Compose (recommended)

A root `Makefile` provides convenience commands for the full stack:

```bash
# Build all services
make docker-build       # build web-app + server
make docker-build-web   # build web-app only
make docker-build-api   # build server only

# Start services
make docker-run         # full stack: web-app, server, db, prometheus, grafana, cadvisor
make docker-run-core    # core only: web-app, server, db (no monitoring)
make docker-run-db      # database only (ENV=development|staging|production)

# Logs
make docker-migrate     # apply Alembic migrations (one-shot container)
make docker-migrate-status  # show the database's current revision

make docker-logs        # follow logs for all services
make docker-logs-core   # follow logs for core services only

# Stop & clean
make docker-stop        # stop all services
make clean              # stop + remove containers, volumes, and networks

# Rebuild from scratch
make rebuild            # clean + full stack
make rebuild-core       # clean + core stack
```

### Database migrations

Migrations are a discrete release phase, not part of app startup. A one-shot
`migrate` service runs `alembic upgrade head` and `server` will not start until
it exits 0, so a failed migration fails the deploy and leaves the previously
running container serving the old image. This is expressed in the compose files
because the deploy target runs only `docker compose up -d --build` and offers no
release-phase hook.

Two consequences worth knowing:

- `depends_on` applies to `compose up`, not to reboots. After a Docker daemon or
  host restart, `server` returns under its restart policy without a `migrate` run.
- Revisions are authored on the host (`cd server && make migrate-create ENV=…`).
  In dev, `server/alembic/` is bind-mounted so the container sees new revisions
  immediately; `alembic.ini` is not, so changes to it need `make docker-build-api`.

For production, use the production compose file directly:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Services will be available at:

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API server | http://localhost:8100 |
| API docs (Swagger) | http://localhost:8100/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |
| cAdvisor | http://localhost:8080 |
| PostgreSQL | localhost:5434 |

### Frontend Development (local)

From `web-app/`:

```bash
# Install all workspace dependencies
pnpm install

# Run the web app
pnpm dev:web    # http://localhost:3000

# Copy and fill env file before starting
cp apps/web/.env.example apps/web/.env.local
```

> **The Docker and native paths are mutually exclusive.** They collide on host ports
> **3000 and 8100**, which the Compose services publish, and on the single static
> `NGROK_DOMAIN`, claimed by both the `ngrok` compose service and `make dev-tunnel`. Stop
> one before starting the other. `make dev-preflight` checks the ports and fails with a
> pointer rather than letting the servers die on a bind error.

Running natively also means migrations are **not** applied for you the way the Docker
`migrate` service does it — run `make migrate ENV=development` from `server/`.

For Clerk webhook work, `make dev-tunnel` exposes the local API at `https://$NGROK_DOMAIN`.
Run the Make target rather than `ngrok` directly — it passes `--authtoken` explicitly, for
the reason set out in [`docs/setup/clerk-webhooks.md`](docs/setup/clerk-webhooks.md).

---

## Testing

```bash
# Backend — from server/
make test              # all tests (APP_ENV=test)
make test-unit         # unit tests only, no database needed
make test-integration  # requires a live database
make test-coverage     # HTML + XML coverage report

# Frontend — from web-app/
pnpm type-check        # tsc --noEmit across the workspace

# Repo-level checks
make check-contract              # committed API artifacts match the routes
bash scripts/verify-infra.sh     # layout, identifiers, compose validity
```

---

## Deploying

`docker-compose.prod.yml` serves **both** staging and production — the environment is
`APP_ENV`, not a second file. It publishes no ports: a reverse proxy is the only ingress,
and on a Dokploy host that proxy is Traefik, discovering containers through the file's
labels.

```bash
make deploy-check                      # staging (default)
make deploy-check DEPLOY_ENV=production
```

This builds and boots the deploy stack under its own Compose project, so a running dev
stack is untouched, then tears itself down. It proves the file parses under `APP_ENV`,
that the web image builds with its own `APP_NAME`, that a failed migration fails the
stack, and that nothing publishes a host port.

**It does not exercise the Traefik labels** — a wrong container port or a router pointing
at an undeclared service surfaces on the first real deploy. Reviewing them is the
substitute; see [`docs/setup/deploy-dokploy.md`](docs/setup/deploy-dokploy.md) for the
review checklist and the Dokploy-specific facts behind it.

---

## Documentation

| Where | What |
|---|---|
| [`docs/`](docs/) | Index of everything below |
| [`docs/setup/clerk.md`](docs/setup/clerk.md) | **Start here** — Clerk dashboard, the `role` claim, `ALLOWED_ORIGINS` |
| [`docs/setup/clerk-webhooks.md`](docs/setup/clerk-webhooks.md) | Webhook endpoint and the dev tunnel |
| [`docs/setup/infrastructure.md`](docs/setup/infrastructure.md) | Root `.env`, Prometheus/Grafana/cAdvisor, and what production omits |
| [`docs/setup/making-it-yours.md`](docs/setup/making-it-yours.md) | Renaming this template for your project |
| [`docs/setup/deploy-dokploy.md`](docs/setup/deploy-dokploy.md) | Dokploy/Traefik operational facts for a first deploy |
| [`CLAUDE.md`](CLAUDE.md), [`server/CLAUDE.md`](server/CLAUDE.md), [`web-app/CLAUDE.md`](web-app/CLAUDE.md) | Working conventions and the most detailed operational notes in the repo |

