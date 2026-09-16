# Web App — Frontend Guide

pnpm monorepo containing one Next.js 16 application backed by a shared UI package.

---

## Workspace Structure

```
web-app/
├── apps/
│   └── web/                # The application (port 3000)
└── packages/
    ├── api-client/        # Generated API client from the OpenAPI spec (packages/api-client)
    ├── auth/              # Role enum, useAppAuth(), getUserRole() (packages/auth)
    ├── core/              # cn(), NavItem, curated copy — no renderer (packages/core)
    ├── ui/                # shadcn/Base UI primitives — WEB ONLY (packages/ui)
    └── components/        # Composed app chrome, built on ui (packages/components)
```

The workspace shape (an `apps/` + `packages/` split with shared UI and auth packages)
is what a second app would reuse — nothing about it is single-app-specific.

### The three UI packages, and why they are three

They stack: `@app/core` ← `@app/ui` ← `@app/components` ← `apps/web`. The split is
by what survives a React Native port, not by taste.

- **`@app/core`** holds everything with no render dependency. It builds with
  `lib: ["esnext"]` and no `"dom"`, so `window` in its own source is a **type error** —
  that is the enforcement, not a convention. `skipLibCheck` is load-bearing alongside it
  (see the comment in its tsconfig); do not flip it off.
- **`@app/ui`** is web-only and permanently so. Base UI, DOM elements, CSS variables,
  `sonner` and `next-themes` do not run on React Native. A native target means a second
  primitives package (react-native-reusables / NativeWind), never an adapter for this one.
- **`@app/components`** is composed chrome that knows the app's nav shape, user model,
  branding and settings surface. It reaches for `next/image`, `next/link` and
  `usePathname`.

Import shapes differ on purpose — the subpath should carry information:

```ts
import { Button, Skeleton } from "@app/ui"              // barrel: @app/ui/button adds nothing
import { Skeleton } from "@app/ui/skeleton"             // subpaths also work
import { AppSidebar } from "@app/components/layout/app-sidebar"   // no barrel
import { SettingsDialog } from "@app/components/settings/settings-dialog"
import { cn } from "@app/core/lib/utils"                          // no barrel
import type { NavItem } from "@app/core/types/nav"
```

`@app/ui`'s `exports` is wildcard-based, so `shadcn add` needs no `package.json` edit —
but its barrel (`packages/ui/src/index.ts`) is still hand-maintained, so **a new primitive
needs a line there** or it is silently missing from `@app/ui`.

---

## Dev Commands

Run from `web-app/`:

```bash
pnpm install               # install all workspace dependencies

pnpm dev:web                # web → http://localhost:3000

pnpm build                 # build all apps
pnpm type-check            # TypeScript check across workspace
pnpm test                  # Vitest, once (also `make test-web` from the repo root)
pnpm test:watch            # Vitest in watch mode
```

Env file must exist before starting:

```bash
cp apps/web/.env.example apps/web/.env.local
```

---

## Lint and Format

```bash
pnpm lint            # ESLint in the app and in packages/ui, packages/components, packages/auth
pnpm format          # Prettier --write (config: .prettierrc, semicolons off)
pnpm format:check    # what the root pre-push hook runs
```

Prettier ignores Markdown and the generated client; orval formats the latter
through the same config, so `make gen-contract` and `pnpm format` agree.

---

## Testing

Vitest + Testing Library, in jsdom. One config at the workspace root
(`vitest.config.mts`) covers every package; `vitest.setup.ts` holds the global stubs.
Nothing gates on the suite yet — no CI step, no pre-push hook — so run it yourself:
`pnpm test`, or `make test-web` from the repo root.

**Tests are co-located with their subjects.** `nav-sidebar.test.tsx` sits next to
`nav-sidebar.tsx`.

```
packages/components/src/layout/nav-sidebar.tsx
packages/components/src/layout/nav-sidebar.test.tsx
```

This deliberately diverges from `server/tests/`, which mirrors `app/` in a parallel tree.
The reason is that files move between packages here routinely — `SettingsDialog` was
promoted from `apps/web` into `packages/components` — and a co-located test rides along
with `git mv`, while a parallel tree has to be remembered. The one time it is not, you get
an orphaned test importing a path that no longer exists. Python's `tests/` convention
exists partly for packaging reasons that do not apply to workspace-internal TypeScript.

One consequence worth knowing: `@app/components` exports `"./*": "./src/*.tsx"`, so a
co-located test is nominally importable as `@app/components/layout/nav-sidebar.test`.
Harmless — the package is `private: true` and never builds — but it is real.

**`*.test.*` is Vitest. `*.spec.*` is Playwright.** Vitest's default `include` matches
both, so `vitest.config.mts` pins it to `.test.` only. E2E specs will live in a top-level
`e2e/` directory (they have no package to co-locate with, since their subject is the
running stack) and must never be run by Vitest — they need a live server and a database.

### Does a component earn a test?

Ask whether it has a **branch** or is a pass-through. Everything in
`packages/ui/src/primitives/` is vendored shadcn — testing it tests Base UI. Most chrome
just forwards props. What earns a test is conditional rendering, state, or a mapping:
`MenuNavigator`'s active-route match, `SettingsDialog`'s tab state and `footerSlot`,
`ServerHealthIndicator`'s status colours, `ClerkUserPanel`'s user mapping.

### Three traps specific to this workspace

1. **A sidebar component needs a `SidebarProvider` wrapper, not just a render.**
   `SidebarMenuButton` calls `useSidebar()`, which throws outside a provider, and
   `MenuNavigator` and `SettingsDialog` both render one. `SidebarProvider` then calls
   `useIsMobile()` → `window.matchMedia`, which jsdom does not implement — hence the stub
   in `vitest.setup.ts`. The wrapper is inlined per test file on purpose; when a third
   file needs it, promote it to an `@app/test-utils` workspace package rather than
   inventing a path alias, which would mean editing six standalone tsconfigs.

2. **`isDevelopment` is computed once at module load** from `process.env.NODE_ENV`
   (`apps/web/src/lib/env-helpers.ts`). Under Vitest it is `false`, so
   `ServerHealthIndicator` silently takes the production path and its whole HoverCard
   branch never renders — the naive test passes while covering half the component.
   Reassigning `process.env.NODE_ENV` mid-test does nothing. Mock the module, with a
   getter if one file needs both sides of the branch (see `server-status.test.tsx`).

3. **Test files are type-checked** by `pnpm type-check`, like any other source. Two
   consequences: a `.catch((e) => e)` typed `unknown` fails the build, and jest-dom's
   matchers need `src/testing.d.ts` in each package that uses them — `vitest.setup.ts`
   belongs to no package's tsconfig, so its augmentation does not reach them.

`vitest.config.mts` forces `NODE_ENV=test` before anything reads it. Do not remove that
line. Vitest only defaults `NODE_ENV` when it is unset, so any caller exporting it decides
how React builds — and the root Makefile `-include`s and exports `apps/web/.env.local`
wholesale. With `NODE_ENV=production` React loads its production build and every render
test fails with an error that points nowhere near the cause.

Related: **do not put `NODE_ENV` in an env file.** Next assigns it per command
(`next dev` → development, `next build` → production) and `@next/env` refuses to override
a variable already present in `process.env`, so the entry is inert for Next and only leaks
into whatever else reads the file. `.env.example` shipped `NODE_ENV=production` for exactly
this reason and it has been removed.

New test files are checked by Prettier (`semi: false`) and, in `apps/web`, `packages/ui`,
`packages/components` and `packages/auth`, by ESLint.

Some tests pin behaviour that is **known to be wrong**, so that a fix is what makes them
change. Those are recorded in [`docs/bugs.md`](./docs/bugs.md); a test asserting a bug
names the entry in a comment.

## Skills to Use

Invoke these skills before starting the relevant task:

| Situation | Skill |
|-----------|-------|
| Designing or building any UI — layouts, components, pages, visual hierarchy | `/frontend-design` |
| Deciding where/how to fetch data from the API | `/nextjs-data-fetching-strategy` |
| Building or refactoring React components | `/react` |
| Adding auth, handling user input, or touching security-sensitive code | `/security-review` |
| Performance optimization — bundle size, rendering, caching | `/vercel-react-best-practices` |

---

## Next.js Version Notice

This project uses **Next.js 16** — APIs and conventions may differ from training data.  
Before writing any Next.js-specific code, read the relevant guide in:

```
node_modules/next/dist/docs/
```

Heed deprecation notices. Do not assume patterns from older versions apply.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 16 + React 19, App Router |
| Language | TypeScript 5 (strict) |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui + **Base UI** (`@base-ui/react`) + Lucide React |
| Auth | Clerk (`@clerk/nextjs`) |
| Data Fetching | TanStack Query v5 — hooks generated by orval (`@app/api-client`) |
| Validation | Zod v4 |
| Notifications | Sonner |
| Package Manager | pnpm (workspaces) |

---

## Critical Rules

### Base UI (NOT Radix)

This project uses **Base UI** (`@base-ui/react`), not Radix UI. Patterns are different:

- Use `render` prop instead of `asChild`
- `DropdownMenuLabel` must be inside `DropdownMenuGroup`

```tsx
// ✅ Correct
<DropdownMenuTrigger render={<Button />}>Trigger</DropdownMenuTrigger>

// ❌ Wrong — Radix pattern, does not work here
<DropdownMenuTrigger asChild><Button>Trigger</Button></DropdownMenuTrigger>
```

### Shared Components

Always check `packages/ui` and `packages/components` before creating a new component.
Where a new one belongs:

| What it is | Where |
|---|---|
| A shadcn/Base UI primitive | `packages/ui/src/primitives/` (via `shadcn add` from `packages/ui`) |
| Composed chrome, reusable, no app-specific wiring | `packages/components/src/` |
| Bound to Clerk, the API client, or this app's routes | `apps/web/src/components/` |
| A shipped example a fork is meant to rewrite | `apps/web/src/components/` |
| A type, constant or pure helper with no rendering | `packages/core/src/` |

The "shipped example" row is the one that is easy to get wrong, because dependencies do not
decide it. `GeneralSettings` imports nothing but `@app/ui` and `next-themes`, so the rows
above it say "promote"; it stays in the app anyway. It has no props and no slot — its body
*is* the customization, and `SETTINGS_TABS` in `(dashboard)/layout.tsx` is the extension point it
hangs off. Ask whether a fork configures the component or rewrites it. Rewrites stay here.

The seam everywhere else is the slot pattern: `AppSidebar` takes `settingsSlot` and
`userSlot`, `SettingsDialog` takes `footerSlot`, and `apps/web` injects the Clerk- and
API-aware pieces. That is also the promotion mechanism — `SettingsDialog` moved into
`packages/components` by turning its one hardcoded `<ServerHealthIndicator />` into
`footerSlot`. Prefer that over importing `@app/auth` or `@app/api-client` into
`packages/components`.

### Server vs Client Components

- Default to **Server Components**
- Add `"use client"` only when needed: event handlers, hooks, browser APIs
- File naming: **kebab-case** (`user-panel.tsx`, `app-sidebar.tsx`)

### Authentication

- **Clerk** handles auth — no login/register endpoints to build
- Client components: `useAppAuth()` from `@app/auth` — never `useUser()` / `useAuth()` directly. Server components: `currentUser()`
- Trust middleware: if a protected route renders, the user is authenticated — no manual auth checks needed
- Use embedded Clerk components (custom routes), not hosted Account Portal

### Clerk RBAC — Auth Package and Role-Gated Rendering

Shared auth logic lives in **`packages/auth`** (`@app/auth`) — not in `packages/ui`. This includes the `Role` enum (`user` | `admin`), `getUserRole()`, `isAdmin()`, `ROLE_LABELS`, and the `AuthProvider` / `useAppAuth()` hook.

This project is on `@clerk/nextjs` **v6 (Core 2)**. The current SDK (`<Show>`) is not available.

**The role has no tenant behind it.** There are no Clerk Organizations in this template.
The platform role is a plain user attribute: set `publicMetadata.role` on the user in
Clerk, and the Clerk dashboard's session token customization copies it onto every
session token as a top-level `role` claim (`{"role": "{{user.public_metadata.role}}"}`
— see `docs/setup/clerk.md`). `AuthProvider` (`packages/auth/src/provider.tsx`) reads
that claim off `sessionClaims.role`, not off Clerk's organization-role field and not off
`sessionClaims.metadata.role`.

**In client components — always use `useAppAuth()`**, never `useAuth()` or `useUser()` directly:

```typescript
import { useAppAuth, Role } from '@app/auth'

const { user, role, isLoaded } = useAppAuth()
if (role === Role.ADMIN) { ... }
```

**No `<Protect role="...">` here.** That prop is Clerk's gate for *organization* roles
(`org:admin`, prefixed), and this template has no organizations — the role is a plain
custom session claim, which `<Protect>`'s `role`/`permission` props do not read. Gate on
it explicitly instead: `useAppAuth()` client-side (above), or `sessionClaims.role` read
server-side / in middleware and passed through `getUserRole()` from `@app/auth`.

**Middleware (`proxy.ts`):** every signed-in user may use the app today; there is no
route matcher gating by role yet. If a route needs one, read `sessionClaims.role` from
`auth()` and pass it through `getUserRole()` — never read Clerk's organization-role
field (there is no org context) and never branch on the raw claim string directly.

### API Client — Generated, Never Hand-Written

Every request and response type comes from `@app/api-client`, generated by orval from
`server/openapi.json`. **A hand-written type describing an API payload is a bug.**

```typescript
import { useGetReadiness } from "@app/api-client/endpoints/system"  // hooks, per tag
import type { ReadinessResponse } from "@app/api-client/types"      // types
import { GetReadinessResponse } from "@app/api-client/zod/system"   // Zod validators
import { ApiError } from "@app/api-client"                          // the error type
```

Rules:

- **Never hand-edit anything under `packages/api-client/src/generated/`.** orval runs
  with `clean: true` and deletes that tree on every generation.
- **Regenerate in the same commit as the server change.** Run `make gen-contract` from
  the repo root, or the **Contract: Generate** VS Code task. `make check-contract` does
  the same and then fails on drift — that is what CI and the image build run, and the
  pre-commit hook blocks a `server/app/` commit that leaves the artifacts behind.
- Import hooks **per tag** (`/endpoints/<tag>`), not from a barrel. Tags come from the
  route's FastAPI tag.
- Streaming routes are deliberately excluded from generation (they carry the `streaming`
  tag), so they have no hook. Call them with plain `fetch`.
- Generated hooks route through `useApiFetch`, which is **a hook** — it reads the live
  Clerk token from `useAppAuth()` on every call. That makes them client-only: a Server
  Component, route handler or script needs its own hand-written fetch.
- Do not create an `src/lib/api/` layer. The generated client is that layer.

**Errors.** Every hook's `error` is an `ApiError` — `{ status, body, requestId }` — and
nothing else. `QueryProvider` toasts centrally, mapping the **status** to curated copy in
`@app/core/constants/messages` (`packages/core/src/constants/messages.ts`) — it lives in
core because a native client hitting the same API needs the identical mapping, and the
rule it encodes (never surface server-authored text) should be inherited, not re-derived.

```typescript
// ✅ Correct — a status maps to copy we wrote
if (error.status === 404) toast.error(messages.toasts.notFound)

// ❌ Wrong — server-authored text must never reach the UI
toast.error(error.message)
toast.error(String(error.body))
```

### Loading States

- Use **component-level skeletons** for auth loading and data fetching
- Use **`loading.tsx`** for route-level navigation loading
- Never return `null` from loading states — always return a skeleton
- Use sidebar-aware skeleton colors: `bg-sidebar-accent`, `bg-muted`, `bg-foreground/10`

### Error Handling

- API payloads are validated with the **generated Zod schemas** (`@app/api-client/zod/*`);
  hand-written schemas are only for non-API input such as forms
- Let TanStack Query's `error` state or an error boundary handle display — see the
  API Client section above for what may and may not be rendered
- Never swallow errors silently

---

## Common Pitfalls

- Using `asChild` (Radix) instead of `render` prop (Base UI)
- Placing `DropdownMenuLabel` outside `DropdownMenuGroup`
- Creating new components in `apps/` that belong in `packages/ui` or `packages/components`
- Returning `null` from loading states
- Using wrong skeleton colors inside sidebars
- Forgetting `"use client"` on components with hooks or event handlers
- Setting `CLERK_JWT_ISSUER_DOMAIN` and expecting it to do something — nothing reads it. The issuer that anchors token validation is the **server's** `CLERK_ISSUER` (`server/app/core/config.py`, `AuthSettings`); the app only needs the publishable key and the sign-in/sign-up URLs
- Using `<Show when={{ role }}>` (current SDK) — not available on this SDK version
- Using `<Protect role="org:...">` — there is no organization; that prop reads org roles, which this template does not have
- Reading `sessionClaims.metadata.role` or Clerk's organization-role field for role checks — the claim is a top-level `sessionClaims.role`, read through `getUserRole()`
- Calling `useAuth()` / `useUser()` directly in components — use `useAppAuth()` from `@app/auth`
- Putting auth logic in `packages/ui` — it belongs in `packages/auth`
- Importing `@app/ui` or anything DOM-flavoured into `packages/core` — it has no `"dom"` lib and will not compile
- Adding a primitive to `packages/ui/src/primitives/` and forgetting the matching line in `packages/ui/src/index.ts`
- Adding a package under `packages/` without a `@source` line in `apps/web/src/styles/globals.css` — Tailwind scans paths, not the package graph, so the build still passes and the UI renders unstyled
- Hand-editing files under `packages/api-client/src/generated/` — the next generation deletes them
- Hand-writing a type for a request or response body — import it from `@app/api-client/types`
- Changing a server route without running `make gen-contract` in the same commit
- Rendering `error.message` or `error.body` — map `error.status` to copy in `@app/core/constants/messages`
- Rendering a sidebar component in a test without wrapping it in `SidebarProvider` — `useSidebar()` throws
- Expecting `isDevelopment` to be true in a test — it is a module-load constant and Vitest sets `NODE_ENV=test`; mock `@/lib/env-helpers`
- Naming a Vitest file `*.spec.ts` — that suffix is reserved for Playwright and is excluded from the Vitest run
