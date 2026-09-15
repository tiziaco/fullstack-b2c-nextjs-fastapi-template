# Making It Yours

How to turn this template into your project: renaming the service and replacing the
branding.

Companion: [`clerk.md`](./clerk.md) for the dashboard side, which §4 depends on.

---

## The one rule

**`server/pyproject.toml` is the single source of the service's public identity, and
changing it is a contract change.** The title lands verbatim in the committed
`server/openapi.json` and in the header of every generated client file. Change it and
regenerate in the *same commit*, or CI fails on the next push.

---

## 1. Service identity

`server/pyproject.toml`:

```toml
[project]
version = "1.0.0"                      # bumping this is also a contract change
description = "..."                    # packaging metadata only

[tool.app.metadata]
title = "Your App - Server"            # → openapi.json info.title, every client header
description = "..."                    # → openapi.json info.description
api_v1_str = "/api/v1"                 # → prefix on every versioned path
```

Then, from the repo root:

```bash
make gen-contract     # rewrites openapi.json + every generated client file
git add -A            # stage the artifacts WITH the pyproject change
```

> **The pre-commit hook will not save you here.** It regenerates only when a commit
> touches `^server/app/` (`.githooks/pre-commit`), and this change touches
> `server/pyproject.toml`. Run `make gen-contract` yourself. CI
> (`.github/workflows/api-contract.yml`, no path filter) is the backstop, so the failure
> surfaces on push rather than at commit.

Verify with `make check-contract` — it regenerates and fails on any drift.

## 2. Frontend identity

In `web-app/apps/web/`:

| What | Where |
|---|---|
| Browser tab title, meta description | `src/app/layout.tsx` → `export const metadata` |
| Sidebar logo alt text | `src/app/(dashboard)/layout.tsx` → `logoAlt` |
| Sidebar mark | `public/images/logo-small.png` |
| Favicon | `public/icons/favicon.ico` |
| Sidebar nav items | `src/lib/hub-nav.ts` → `HUB_NAV` |
| Error toast copy | `src/lib/messages.ts` → `messages.toasts` |

The two image files are the only branding a text search cannot find. They are rendered
through `packages/ui/src/components/layout/company-logo.tsx`.

## 3. Docker, Compose and deploy identity

| Setting | Where | What it actually names |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | root `.env` | Compose project, image tags, **and every Traefik router/service label** in `docker-compose.prod.yml` |
| `PROJECT_NAME` | `server/.env.<env>` | the image tag built by `make -C server docker-build`, and nothing else |
| fallback image name | `server/scripts/docker-image-name.sh` | used when `PROJECT_NAME` is unset on a fresh clone |
| `WEB_DOMAIN`, `API_DOMAIN` | deploy environment | the hostnames Traefik routes |

> `PROJECT_NAME` is **not** the API's title, despite the name. It tags Docker artifacts.
> The API title is §1. The two are free to differ and setting one does nothing to the
> other.

Verify with `make deploy-check` (and `make deploy-check DEPLOY_ENV=production`). Note
what it does *not* prove — the Traefik labels themselves are never exercised; see
[`deploy-dokploy.md`](./deploy-dokploy.md) for the review checklist.

## 4. The example domain

The template ships **no** example domain — no domain model, no seeded routes beyond
`GET /api/v1/admin/ping`. That endpoint exists purely to prove the role guard end to
end: see `server/app/api/dependencies/authorization.py` (`require_role()`, `AdminOnly`)
and `server/app/api/v1/admin.py`. Build your domain directly on the auth, contract and
deploy machinery — there is nothing shipped to rip out first.

The one thing worth knowing before you touch roles:

- **Renaming a role is a dashboard change too.** Change the enum in
  `server/app/models/enums.py` **and** `web-app/packages/auth/src/permissions.ts`
  without also updating `publicMetadata.role` on existing Clerk users, and those users
  silently lose access — `getUserRole()` returns `null` for a value the enum no longer
  recognises, and every role-gated route or component treats them as unauthenticated.

## 5. Verify the whole rename

```bash
make check-contract              # artifacts match the code that produces them
bash scripts/verify-infra.sh     # layout, identifiers, compose validity
make deploy-check                # the deploy file parses and the stack reaches healthy
cd server && make test           # nothing behavioural moved
```

None of those checks knows your old name. To confirm it is gone, search the tracked
files yourself — `git grep`, not `grep -r`, so gitignored local state (`server/.env.*`,
`server/logs/`) does not report a failure that no rename can fix:

```bash
git grep -Ii your-old-name
```

---

## A trap worth knowing before a first deploy

**`ALLOWED_ORIGINS` gates auth, not just CORS.** A missing web-app origin looks like
broken authentication, not a config error. [`clerk.md`](./clerk.md) §4.

The `NEXT_PUBLIC_*` build-args mechanism is also worth understanding before a second app
joins this one: Compose resolves `build.args` from the invoking shell's environment, not
from a service's own `env_file:`, and the Makefile's `-include` exports only
`web-app/apps/web/.env.local`. Not yet a trap with one app — but the day a second app is
added, both images build with whichever app's `.env.local` the Makefile happens to
export, with nothing warning that the other app's values were never read.
