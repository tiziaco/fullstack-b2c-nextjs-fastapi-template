# Documentation

## Start here

| Doc | What it covers |
|---|---|
| [`setup/clerk.md`](./setup/clerk.md) | Clerk dashboard setup — the `role` claim, keys, `ALLOWED_ORIGINS`. **Do this first; nothing authenticates without it.** |
| [`setup/clerk-webhooks.md`](./setup/clerk-webhooks.md) | Webhook endpoint, signing secret, and the ngrok tunnel for local delivery |
| [`setup/infrastructure.md`](./setup/infrastructure.md) | The root `.env`, and the Prometheus/Grafana/cAdvisor stack — what it covers, and what production does not |
| [`setup/making-it-yours.md`](./setup/making-it-yours.md) | Renaming the template for your project — service identity, branding, deploy names |
| [`setup/deploy-dokploy.md`](./setup/deploy-dokploy.md) | Dokploy/Traefik operational facts for a first deploy — what `make deploy-check` cannot exercise |

## Reference

| Doc | What it covers |
|---|---|
| [`api-client-codegen-setup.md`](./api-client-codegen-setup.md) | Rebuild guide for the OpenAPI → orval → TanStack Query pipeline |

Service-level docs live next to their code:

- [`../server/docs/authentication.md`](../server/docs/authentication.md) — how the server verifies a token and provisions a user
- [`../server/docs/gdpr-compliance-guide.md`](../server/docs/gdpr-compliance-guide.md) and [`gdpr-erasure-findings.md`](../server/docs/gdpr-erasure-findings.md)
- [`../web-app/docs/bugs.md`](../web-app/docs/bugs.md) — known-broken web behaviour, with repro steps and what fixing it involves
- [`../CLAUDE.md`](../CLAUDE.md), [`../server/CLAUDE.md`](../server/CLAUDE.md), [`../web-app/CLAUDE.md`](../web-app/CLAUDE.md) — working conventions, and the most detailed operational notes in the repo
