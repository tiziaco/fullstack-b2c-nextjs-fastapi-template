# Template App — Web App

pnpm monorepo containing the template's Next.js frontend app, built on one shared
component library and one generated API client.

## Structure

```
web-app/
├── apps/
│   └── web/                # The application (port 3000)
└── packages/
    ├── api-client/        # @app/api-client — generated API client from the OpenAPI spec
    ├── auth/              # @app/auth — Role enum, useAppAuth(), getUserRole()
    ├── core/              # @app/core — cn(), NavItem, copy; no renderer, no DOM
    ├── ui/                # @app/ui — shadcn/Base UI primitives (web only)
    └── components/        # @app/components — composed app chrome, built on @app/ui
```

## Tech Stack

- **Next.js 16** + React 19 + TypeScript 5
- **Tailwind CSS v4** + shadcn/ui
- **Clerk** for authentication (`@clerk/nextjs`)
- **TanStack Query v5** for data fetching and caching
- **Zod v4** for schema validation
- **Sonner** for toast notifications
- **pnpm workspaces** for monorepo management

## Setup

```bash
# From web-app/
pnpm install

# Copy and fill in environment variables
cp apps/web/.env.example apps/web/.env.local
```

Key variables in `.env.local`:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
CLERK_SECRET_KEY=...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_API_URL=http://localhost:8100
```

## Development Commands

```bash
# From web-app/
pnpm dev:web         # the app at http://localhost:3000
pnpm build           # production build for all apps
pnpm type-check      # TypeScript check across all packages
```

## Managing Packages

### Where to add a dependency

| Dependency type | Where to add |
|-----------------|--------------|
| Runtime dep used by the app | `apps/web` |
| Needed by a primitive | `packages/ui` |
| Needed by composed chrome | `packages/components` |
| Pure helper, type or constant — no rendering | `packages/core` |
| Tooling (eslint, typescript, etc.) | Workspace root (`-w`) |

```bash
# Add to the app
pnpm --filter web add <package>

# Add to a shared package
pnpm --filter @app/ui add <package>
pnpm --filter @app/components add <package>
pnpm --filter @app/core add <package>

# Add to the workspace root (tooling only)
pnpm add -w <package>
```

`@app/core` compiles without the `dom` lib on purpose, so anything browser-flavoured
does not belong there — the type checker will say so.

### Adding shadcn components

shadcn primitives belong in `packages/ui`. Run from that directory — it holds the only
`components.json` in the repo:

```bash
cd packages/ui && pnpm dlx shadcn@latest add button dialog table
```

Components land in `packages/ui/src/primitives/` and are importable immediately as
`@app/ui/button`: the package's `exports` is a wildcard, so **no `package.json` edit is
needed**. The barrel is a separate matter — `packages/ui/src/index.ts` is hand-maintained,
so add a line there too or the component is missing from `import { … } from "@app/ui"`.

A component composed out of those primitives, with no Clerk or API-client wiring, belongs
in `packages/components`. One bound to this app's auth, routes or API payloads belongs in
`apps/web/src/components/` — as does a shipped example a fork is meant to rewrite rather
than configure, even when it has no such wiring. `GeneralSettings` is the second kind;
`web-app/CLAUDE.md` has the full rule.

## Docker Commands

```bash
make docker-build   # build Docker image
make docker-run     # run container on port 3000
make docker-stop    # stop and remove container
make docker-logs    # follow container logs
make docker-clean   # stop, remove container and image
```

> For running the full stack (frontend + backend + db), use the root `Makefile`. See the root `README.md`.
