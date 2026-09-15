# Deploying with Dokploy

Operational facts for deploying `docker-compose.prod.yml` behind Dokploy's Traefik
instance. Companion to the **Deploying** section of the root [`CLAUDE.md`](../../CLAUDE.md):
that section covers `make deploy-check` and what it proves; this doc covers the Traefik
side that `deploy-check` cannot exercise.

---

## How Dokploy actually configures Traefik

Established from the Dokploy documentation and source, not assumed:

- **Providers:** Docker + Swarm with `exposedByDefault: false`, plus a file provider for
  shared middleware. For a Compose application, routing comes from **Docker labels** —
  not from a separately generated config.
- **Entrypoints:** `web` (port 80), `websecure` (port 443).
- **Cert resolver:** named `letsencrypt`, HTTP challenge. Applied only to `websecure`
  routers, never to `web` — a `tls.certresolver` label enables TLS on whatever entrypoint
  its router is bound to, so putting it on the `web` router would make port 80 expect a
  TLS handshake. That is why `docker-compose.prod.yml` declares two routers per service
  (`<name>-web` and `<name>-secure`) instead of one router with a variable entrypoint.
- **Network:** `dokploy-network`. Traefik is pinned to it. **A Compose deployment lands
  only in its own project network unless the compose file joins `dokploy-network`
  explicitly** — this repo's `docker-compose.prod.yml` does (see `networks:` on `web`
  and `server`). This is a known, still-open Dokploy issue
  ([#3435](https://github.com/Dokploy/dokploy/issues/3435)) and the single most common
  cause of a deploy that builds cleanly and then 404s. If a first deploy 404s, check this
  before anything else.

**Dokploy's Domains tab and hand-written labels are both labels, not two different
mechanisms.** Configuring a domain in the Domains UI and hand-writing a `Host()` label
for the same service both produce Traefik router labels. Doing both for the same
service yields two routers matching the same `Host()` rule, which is ambiguous —
confirmed by Dokploy issue [#3222](https://github.com/Dokploy/dokploy/issues/3222)
(the Domains tab does not show label-configured domains, because hand-written labels are
a recognised, separate path). **This template hand-writes every label in
`docker-compose.prod.yml` and leaves the Domains tab untouched.** Do not add a domain
there for a service this file already labels.

Sources: [Domains — Docker Compose](https://docs.dokploy.com/docs/core/docker-compose/domains),
[Domains](https://docs.dokploy.com/docs/core/domains),
[Traefik configuration](https://deepwiki.com/Dokploy/dokploy/8.2-traefik-configuration),
[#3435](https://github.com/Dokploy/dokploy/issues/3435),
[#3222](https://github.com/Dokploy/dokploy/issues/3222).

---

## `ALLOWED_ORIGINS` gates auth, not just CORS

`ALLOWED_ORIGINS` (`server/app/core/config.py:217`) feeds **two** consumers:

- CORS (`server/app/api/middlewares/cors.py`)
- the Clerk `azp` token-party check (`server/app/utils/auth.py:72`)

Every origin introduced at deploy time — the web app's real hostname — must be listed
there for the matching environment (`server/.env.staging` / `server/.env.production`),
or a structurally valid, correctly-signed Clerk token is rejected on arrival. **A missing
entry does not look like a config error; it looks like broken auth** — `401` with a
`token_party_not_allowed` log line, not a startup failure.

It matters more than it looks because the browser calls the API **directly,
cross-origin**: there is no server-side proxy hop hiding the origin. This is unexercised
by anything short of a real deploy — no browser, no Clerk, no CORS preflight runs during
`make deploy-check`.

---

## What `make deploy-check` does not prove

`make deploy-check` (`scripts/deploy-check.sh`) parses the compose file, builds the `web`
and `server` images, brings the stack up under `APP_ENV=staging` (or `production`), and
asserts `migrate` exits 0, `server` reaches `healthy` through its own healthcheck, and
nothing is published to the host. **It does not route a single request through Traefik.**

Nobody has exercised the current label set against a real Traefik instance. Before the
first real deploy, review each of the following by hand against the Dokploy facts above — a
`docker compose config` render of `docker-compose.prod.yml` is enough, no server needed:

- `traefik.enable=true` is present on `web` and `server` (not on `db` or `migrate`,
  which are not routable).
- `traefik.docker.network=dokploy-network` is present on both routable services.
- Each service declares **two** routers — `-web` (entrypoint `web`, no TLS) and
  `-secure` (entrypoint `websecure`, `tls.certresolver=letsencrypt`) — both pointing at
  the same `traefik.http.services.<name>.loadbalancer.server.port`.
- The container port in that `loadbalancer.server.port` label matches what the container
  actually listens on (`3000` for `web`, `8000` for `server`).
- The `server` routers exclude `/metrics`: `Host(...) && !PathPrefix(`/metrics`)`. That
  endpoint carries no auth, and a bare `Host()` rule would route it publicly.
- `WEB_DOMAIN` and `API_DOMAIN` are set to real hostnames in the Dokploy environment —
  nothing resolves them locally, so a typo renders a label that matches no traffic
  instead of erroring.

None of this is exercised until the first deploy. A wrong container port, a router
pointing at a service that is not declared, or a missing `dokploy-network` join each
surfaces there — as a 404 with nothing in the application logs to explain it, because
the request never reached the application.

---

## Also unproven until a first deploy

- **No TLS.** The `letsencrypt` cert resolver's HTTP challenge is first exercised on a
  real deploy — there is nothing to issue a certificate for locally.
- **No Dokploy.** Its label injection, build pipeline, and `dokploy-network` creation are
  unexercised by anything in this repo.

---

## If a deploy builds cleanly and then 404s

In order of likelihood, given the facts above:

1. The service is not on `dokploy-network` (check `networks:` in
   `docker-compose.prod.yml`, and that `docker network create dokploy-network` — or its
   Dokploy-managed equivalent — has actually run on the host).
2. A domain was also added in the Dokploy Domains tab for a service this file already
   labels, producing two ambiguous routers for the same `Host()`.
3. `WEB_DOMAIN` / `API_DOMAIN` in the Dokploy environment does not match the hostname
   actually being requested.
