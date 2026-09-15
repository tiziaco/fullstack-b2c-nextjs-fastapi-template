# Infrastructure — the root `.env` and the monitoring stack

What the root `.env` is for, what `infra/` contains, and what the monitoring stack does
and does not cover.

Nothing here is needed to run the app. `make docker-run-core` starts the web app, the
server and the database without any of it. Read this when you want dashboards, or when
`make docker-run` fails on a variable you have never heard of.

---

## 1. The root `.env`

Distinct from the service env files, and easy to miss:

| File | Configures |
|---|---|
| **`.env`** (repo root) | Docker Compose orchestration — this file |
| `server/.env.<environment>` | FastAPI: database, Clerk, LLM, rate limits |
| `web-app/apps/web/.env.local` | Next.js: `NEXT_PUBLIC_*` build args, Clerk keys |

```bash
cp .env.example .env
```

The root `Makefile` loads it with `-include`, which is also how its values reach Compose:
the `--env-file` flag on the docker targets points at `server/.env.<env>` *instead of*
the root `.env`, not in addition to it.

| Variable | Purpose |
|---|---|
| `APP_ENV` | Selects the server env file Compose loads (`./server/.env.${APP_ENV}`). Default `development`. |
| `GRAFANA_ADMIN_PASSWORD` | Grafana's admin password. Required whenever Grafana starts — see §4. |
| `NGROK_DOMAIN` | Your reserved ngrok domain, for Clerk webhook delivery |
| `NGROK_AUTHTOKEN` | ngrok authtoken. See [`clerk-webhooks.md`](./clerk-webhooks.md). |

Two more are honoured but **not in `.env.example`**, because the defaults are usually
right. Add them only on a machine where the defaults collide:

| Variable | Default | Why you would set it |
|---|---|---|
| `API_HOST_PORT` | `8100` | 8000 is what every other FastAPI project on the machine also wants. Host-side only — the container still listens on 8000, so the healthcheck, the Prometheus target and `server:8000` are unaffected. |
| `POSTGRES_HOST_PORT` | `5434` | 5432 collides with a local Postgres. Host-side only; on the compose network `db` is always 5432. |

---

## 2. The monitoring stack

Started by `make docker-run`, **not** by `make docker-run-core`.

| Service | URL | Role |
|---|---|---|
| Prometheus | http://localhost:9090 | Scrapes and stores metrics |
| Grafana | http://localhost:3001 | Dashboards (container port 3000) |
| cAdvisor | http://localhost:8080 | Per-container CPU, memory, network, disk |

Grafana signs in as **`admin`** with the password from `GRAFANA_ADMIN_PASSWORD`.
Self-signup is off (`GF_USERS_ALLOW_SIGN_UP=false`). Dashboards you edit in the UI persist
in the `grafana-storage` volume and survive a restart — but not `make clean`, which
removes volumes. Anything worth keeping belongs in `infra/grafana/dashboards/json/`.

### What is provisioned

Everything under `infra/` is bind-mounted into the containers at startup, so the stack
comes up configured — there is no manual setup step.

```
infra/
├── prometheus/prometheus.yml           # scrape config
└── grafana/
    ├── datasources/datasource.yml      # Prometheus at http://prometheus:9090, default
    ├── dashboards/dashboards.yml       # provider: load every JSON in json/
    └── dashboards/json/
        ├── api_overview.json           # API Overview — 8 panels
        ├── infrastructure.json         # Infrastructure — 3 panels
        └── llm_latency.json            # LLM & Agent Tools — 12 panels
```

Prometheus scrapes two targets every 15s — `server:8000/metrics` and `cadvisor:8080` —
over the compose network, so neither needs a host port for scraping to work. Retention is
30 days or 10 GB, whichever comes first.

### The dashboards depend on a label contract

`server/app/api/middlewares/prometheus.py` sets non-default instrumentation options
(`should_group_status_codes=False`, wider latency buckets) specifically to produce the
labels the committed dashboards query. Changing them does not error — the panels just go
empty. `tests/unit/middleware/test_metrics_setup.py` guards this.

Business metrics (`llm_*`) live in `app/core/metrics.py`. The HTTP families
(`http_requests_total`, `http_request_duration_seconds`) come from the instrumentator and
**only** from there: registering either name elsewhere makes the library swallow a
`ValueError` and emit no HTTP metrics at all, silently.

---

## 3. Production has no monitoring

`docker-compose.prod.yml` ships four services — `web`, `migrate`, `server`, `db`. No
Prometheus, no Grafana, no cAdvisor. The stack is instrumented (the server still serves
`/metrics`) but nothing scrapes it.

That is a deliberate gap, not an oversight to work around casually: adding Prometheus to a
Dokploy host means deciding where the data lives, who can reach the dashboards, and
whether the endpoint stays reachable only inside `app-network` (see §5).

---

## 4. Why `make docker-run` can fail when `docker-run-core` does not

```
GRAFANA_ADMIN_PASSWORD is required
```

The Grafana service declares `${GRAFANA_ADMIN_PASSWORD:?…}`. Compose evaluates that guard
only for services it is actually starting, so `docker-run-core` — which names its four
services explicitly — never touches it. `docker-run` starts everything, including Grafana,
and stops with that message.

It is Compose's own error, and it names the variable. Set it in the root `.env`.

---

## 5. Two exposure notes worth reading before a deploy

For the Dokploy/Traefik side of a deploy — network membership, label review, the
`ALLOWED_ORIGINS` trap — see [`deploy-dokploy.md`](./deploy-dokploy.md).

**cAdvisor runs `privileged: true` and mounts `/var/run/docker.sock`.** It needs that to
read container stats, but it means anything reaching cAdvisor can enumerate every
container on the host — not just this stack's. It publishes port 8080 to the host in the
dev file. Fine on a laptop; think before putting it on a shared machine.

**`/metrics` is unauthenticated.** The endpoint is mounted by the instrumentator with no
auth dependency, and `AuthMiddleware` never rejects a request — it parses a token when one
is present and otherwise carries on. In prod the Traefik routers therefore exclude it
explicitly:

```
Host(`${API_DOMAIN}`) && !PathPrefix(`/metrics`)
```

The endpoint stays mounted and reachable on `app-network`, so a Prometheus service added
to the prod file later still scrapes it. This is a denylist: **another operational path
added to the API must be excluded here too**, and `make deploy-check` will not notice if
it is not — it does not exercise Traefik labels at all.

**Related, and deliberately unchanged:** `server/app/main.py` disables `/docs`, `/redoc`
and `/openapi.json` when `ENVIRONMENT == PRODUCTION`. `docker-compose.prod.yml` serves
staging *and* production, so on **staging those three are served and publicly routed**.
Whether that is acceptable depends on your product — a public consumer API's schema is
often fine to expose; decide deliberately rather than by default. The gate in `main.py`
is where to narrow or widen it.

---

## Symptom → cause

| What you see | Likely cause |
|---|---|
| `GRAFANA_ADMIN_PASSWORD is required` | Root `.env` missing or lacks the variable (§4). `docker-run-core` avoids Grafana entirely. |
| Grafana loads, every panel empty | Prometheus cannot reach `server:8000`. Check the server container is up and on `app-network`. |
| Some panels populated, others empty | Label contract broken — instrumentation options changed (§2). |
| Grafana rejects `admin`/`admin` | The username is `admin`; the password is whatever `GRAFANA_ADMIN_PASSWORD` is set to in the root `.env`. |
| Port 5432 or 8000 already allocated | Set `POSTGRES_HOST_PORT` / `API_HOST_PORT` in the root `.env` (§1). |
| Dashboards vanished after `make clean` | `clean` removes volumes, including `grafana-storage`. Commit dashboards to `infra/grafana/dashboards/json/`. |
| Metrics work locally, absent in prod | Expected — the prod compose file ships no monitoring stack (§3). |
