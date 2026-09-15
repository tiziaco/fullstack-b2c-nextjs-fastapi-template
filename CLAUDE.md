# Template App — Monorepo Guide

Template for a B2C application: one Next.js frontend backed by a single FastAPI server.
Auth and the platform role both come from Clerk — the role is a custom `role` claim on
the session token, sourced from `publicMetadata.role`, not from Clerk Organizations
(there are none).

The template ships **no example domain.** `GET /api/v1/admin/ping` is the worked
example of the role guard — see `server/app/api/v1/admin.py`. Replace or extend it with
real endpoints.

**Two platform roles:** `user` and `admin` (`server/app/models/enums.py`,
`web-app/packages/auth/src/permissions.ts`).

---

## Repo Structure

```
app/
├── server/               # FastAPI backend (Python 3.13, uv)
├── web-app/              # Next.js monorepo (pnpm workspaces)
│   ├── apps/
│   │   └── web/                # The application (port 3000)
│   └── packages/
│       ├── api-client/        # @app/api-client — generated API client from the OpenAPI spec
│       ├── auth/              # @app/auth — Role enum, useAppAuth(), getUserRole()
│       └── ui/                # @app/ui — shared component library (shadcn/ui)
├── infra/                # Infrastructure config
│   ├── prometheus/            # Prometheus scrape config
│   └── grafana/               # Grafana datasources and dashboards
├── docker-compose.dev.yml     # Development stack
└── docker-compose.prod.yml
```

See `server/CLAUDE.md` and `web-app/CLAUDE.md` for service-specific conventions.

---

## Running the Stack

There are two ways to run this app, and **they are mutually exclusive**:

- **Docker path** — everything in Compose (`make docker-run`). Includes ngrok.
- **Native path** — app processes on the host, Postgres still in Docker
  (VS Code's `Dev: *` tasks). Needs its own host-side tunnel.

They collide on two resources: host ports **3000 and 8100**, which the
compose services publish; and the single static **`NGROK_DOMAIN`**, claimed by
both the `ngrok` compose service and `make dev-tunnel`. Stop one path before
starting the other — `make dev-preflight` checks the ports and fails with a
pointer rather than letting the servers die on a bind error.

### Native dev

```bash
make dev-preflight      # verify ports 8100/3000 are free
make dev-tunnel         # ngrok: https://$NGROK_DOMAIN -> localhost:8100
```

`NGROK_DOMAIN` and `NGROK_AUTHTOKEN` come from the root `.env` (loaded by the
Makefile via `-include`), not from your shell — so run the target rather than
`ngrok` directly. It passes `--authtoken` explicitly, for the reason in
[`docs/setup/clerk-webhooks.md`](docs/setup/clerk-webhooks.md).

In VS Code, `Dev: All` (⇧⌘B) chains preflight → start db → migrate → API server
and the web app. `Dev: All + Tunnel` adds the tunnel, for Clerk webhook work.
Migrations are **not** applied automatically on this path the way the Docker
`migrate` service does it — `Dev: Migrate` runs `make migrate ENV=development`
on the host.

### Docker

The root `Makefile` manages the full Docker Compose stack.

```bash
# Start
make docker-run         # full stack: web app, server, db, prometheus, grafana, cadvisor, ngrok (dev)
make docker-run-core    # core only: web app, server, db
make docker-run-db      # database only (ENV=development|staging|production)

# Build
make docker-build       # build all services
make docker-build-web   # build web-app only
make docker-build-api   # build server only

# Migrations (applied automatically on `docker-run*`; these are for on-demand use)
make docker-migrate         # apply Alembic migrations in a one-shot container
make docker-migrate-status  # print the database's current revision

# Logs
make docker-logs        # follow all services
make docker-logs-core   # follow core services only

# Stop / clean
make docker-stop        # stop all services
make clean              # stop + remove containers, volumes, networks
make rebuild            # clean + full stack
make rebuild-core       # clean + core stack
```

### Service URLs (Docker)

| Service           | URL                        |
|-------------------|----------------------------|
| Web App           | http://localhost:3000      |
| API server        | http://localhost:8100      |
| Swagger docs      | http://localhost:8100/docs |
| Prometheus        | http://localhost:9090      |
| Grafana           | http://localhost:3001      |
| cAdvisor          | http://localhost:8080      |
| PostgreSQL        | localhost:5434             |
| ngrok (dev only)  | n/a                        |

`ngrok` (dev only) tunnels `server:8000` for Clerk webhook delivery. Compose
publishes no host port for it, so its inspection dashboard has no fixed URL.

---

## Deploying

`docker-compose.prod.yml` is the deploy file, and it serves **both** staging
and production — the environment is `APP_ENV`, not a second file. It publishes
no ports: a reverse proxy is the only ingress, and on a Dokploy host that proxy
is Traefik, discovering the containers through the labels in the file.

```bash
make deploy-check                     # staging (default)
make deploy-check DEPLOY_ENV=production
```

It runs under its own compose project, so a running dev stack is untouched, and
it tears itself down afterwards. It needs `server/.env.<env>` (gitignored, never
committed) and, once per machine, `docker network create dokploy-network` — the
deploy file declares that network `external` because a Dokploy host provides it.

**What it proves:** the file parses under `APP_ENV`; the web image builds with its
own `APP_NAME`; a failed migration fails the stack instead of starting the server
against a stale schema; the server reaches healthy with no ingress but its own
healthcheck; nothing publishes a host port.

**What it does not prove: the Traefik labels.** Nothing routes a request through
a proxy. A wrong container port, a router pointing at a service that isn't
declared, a missing `dokploy-network` — each surfaces on the first real deploy,
not here. Reviewing them is the substitute; see
[`docs/setup/deploy-dokploy.md`](docs/setup/deploy-dokploy.md) for the review
checklist and the Dokploy-specific facts behind it.

Also unproven, and worth knowing before a first deploy: `ALLOWED_ORIGINS`
(`server/app/core/config.py:217`) gates **both** CORS and the Clerk `azp`
token-party check (`server/app/utils/auth.py:72`). The browser calls the API
cross-origin — there is no server-side proxy hop — so the web app's origin must
be listed for the deploying environment. A missing entry does not look like a
config error; it looks like broken auth.

Also worth knowing: `NEXT_PUBLIC_*` values are inlined into the web image at
build time, and Compose resolves `build.args` from the invoking shell's
environment, never from the service's own `env_file:` — the Makefile's
`-include` exports only `web-app/apps/web/.env.local`. With one app this is not
yet a trap, but it is the mechanism a second app would need to know about: a
`build.args` value is always whatever the invoking shell happened to export,
not whatever `env_file:` the service declares.

---

## Environment Setup

Each service has its own env file. Copy examples and fill in values before first run:

```bash
cp .env.example .env   # required by the root Makefile (APP_ENV, GRAFANA_ADMIN_PASSWORD, etc.)
cp server/.env.example server/.env.development
cp web-app/apps/web/.env.example web-app/apps/web/.env.local
```

Required secrets: Clerk API keys, database credentials, OpenAI key, Langfuse key.

The `server/.env.<ENV>` file is selected by the `APP_ENV` variable (default: `development`).

Install the repo's git hooks once per clone:

```bash
git config core.hooksPath .githooks
```

Two hooks live there. `pre-commit` keeps the API contract in sync (see **API
Contract** below). `pre-push` runs `make check-server` and `make check-web`
for whichever side changed since the upstream branch: ruff and Prettier in
check mode, plus ESLint. There is no CI for these, so the hook is the gate;
`make check` runs both by hand and `git push --no-verify` skips it once.
`.vscode/settings.json` formats on save with the same tools, so the hook
rarely has anything to say.

---

## API Contract

`server/openapi.json` and `web-app/packages/api-client/src/generated/` are
generated from `server/app/` and **committed**. They are a published interface,
not a build artifact: the generated tree is what the web app compiles against.

```bash
make gen-contract     # re-export the spec and regenerate the client
make check-contract   # regenerate, then fail if anything moved (what CI runs)
```

### Renaming the service (forks)

The API's title, description and `/api/v1` prefix live in `[tool.app.metadata]`
in `server/pyproject.toml`, its version in that file's `[project]`. Change them
there, run `make gen-contract`, and commit the regenerated artifacts.

They are **not** env variables on purpose: they land in the committed
`openapi.json` and in the header of every generated client file, so reading them
from a gitignored `.env.<env>` would make the artifact differ per machine and
fail `check-contract` for everyone else the moment anyone set one.
`server/.env.example`'s `PROJECT_NAME` is unrelated — it only names Docker
images and containers.

Four checkpoints, each catching what the last one lets through:

| When | What | On drift |
|---|---|---|
| You change a route | `make gen-contract`, or the **Contract: Generate** VS Code task | regenerates |
| You commit | `.githooks/pre-commit`, if the commit touches `server/app/` | regenerates, then blocks |
| You build an image | `make docker-build` / `docker-build-web` gate on `check-contract` | fails the build |
| You push | `.github/workflows/api-contract.yml` | fails CI |

Nothing runs on save, and nothing is wired into the `Dev:` task chain.
Exporting the spec imports `app.main`, so a half-finished refactor would stop
the dev servers from starting — and drift is the normal state while a route is
being written. The gates sit where an inconsistent artifact would actually
escape: a commit, an image, a push.

`git commit --no-verify` bypasses the hook for a single commit; CI still holds.

---

## Tech Stack Summary

| Layer       | Technology                                   |
|-------------|----------------------------------------------|
| Backend     | FastAPI, SQLModel, PostgreSQL 16 + pgvector  |
| AI / Agents | LangGraph, LangChain, Mem0, Langfuse         |
| Auth        | Clerk (shared across backend and frontend)   |
| Frontend    | Next.js 16 (App Router), React 19, TypeScript |
| Styling     | Tailwind CSS v4, shadcn/ui, Base UI          |
| Data        | TanStack Query v5, Zod v4                    |
| Monitoring  | Prometheus + Grafana + cAdvisor              |
| Containers  | Docker + Docker Compose                      |
