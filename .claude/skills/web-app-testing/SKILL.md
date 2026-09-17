---
name: web-app-testing
description: >
  Writing, running and debugging tests in the Next.js workspace (Vitest + Testing Library in jsdom).
  Use whenever adding or changing a test under web-app/, deciding whether a component needs one,
  debugging a test that fails for no obvious reason or passes while covering nothing, touching
  vitest.config.mts or vitest.setup.ts, rendering a sidebar component in a test, or hitting a
  type-check error that only appears in a test file. Trigger on "write a test for X", "add tests",
  "this test fails", "useSidebar is not defined", "matchMedia is not a function", "does this need a
  test", "set up the test environment", or any work touching *.test.tsx under web-app/. Read this
  before writing the first test in a file — three of the four traps below produce failures that point
  nowhere near their cause.
---

# Web App Testing

Vitest + Testing Library, in jsdom. One config at the workspace root (`web-app/vitest.config.mts`)
covers every package; `vitest.setup.ts` holds the global stubs.

```bash
pnpm test          # from web-app/, once
pnpm test:watch    # watch mode
make test-web      # same, from the repo root
```

Nothing gates on the suite — no CI step, no pre-push hook — so run it yourself.

## Does a component earn a test?

Ask whether it has a **branch** or is a pass-through.

Everything in `packages/ui/src/primitives/` is vendored shadcn — testing it tests Base UI. Most
chrome just forwards props.

What earns a test is conditional rendering, state, or a mapping:

- `MenuNavigator`'s active-route match
- `SettingsDialog`'s tab state and `footerSlot`
- `ServerHealthIndicator`'s status colours
- `ClerkUserPanel`'s user mapping

## Four traps specific to this workspace

Three of these produce a failure — or a false pass — that points nowhere near its cause.

### 1. Sidebar components need a `SidebarProvider` wrapper

`SidebarMenuButton` calls `useSidebar()`, which throws outside a provider. `MenuNavigator` and
`SettingsDialog` both render one.

`SidebarProvider` then calls `useIsMobile()` → `window.matchMedia`, which jsdom does not implement —
hence the stub in `vitest.setup.ts`.

The wrapper is inlined per test file on purpose. When a third file needs it, promote it to an
`@app/test-utils` workspace package rather than inventing a path alias, which would mean editing six
standalone tsconfigs.

### 2. `isDevelopment` is a module-load constant — the naive test silently covers half the component

`apps/web/src/lib/env-helpers.ts` computes it once at module load from `process.env.NODE_ENV`. Under
Vitest that is `false`, so `ServerHealthIndicator` takes the production path and its entire HoverCard
branch never renders. **The test passes while covering nothing.**

Reassigning `process.env.NODE_ENV` mid-test does nothing. Mock the module — with a getter if one file
needs both sides of the branch. See `server-status.test.tsx`.

### 3. Test files are type-checked

`pnpm type-check` treats them like any other source. Two consequences:

- A `.catch((e) => e)` typed `unknown` fails the build.
- jest-dom's matchers need `src/testing.d.ts` in **each package that uses them** — `vitest.setup.ts`
  belongs to no package's tsconfig, so its augmentation does not reach them.

### 4. `NODE_ENV` must stay pinned in `vitest.config.mts`

That file forces `NODE_ENV=test` before anything reads it. **Do not remove that line.**

Vitest only defaults `NODE_ENV` when it is unset, so any caller exporting it decides how React
builds — and the root Makefile `-include`s and exports `apps/web/.env.local` wholesale. With
`NODE_ENV=production`, React loads its production build and every render test fails with an error
that points nowhere near the cause.

Related: **do not put `NODE_ENV` in an env file.** Next assigns it per command (`next dev` →
development, `next build` → production) and `@next/env` refuses to override a variable already
present in `process.env`, so the entry is inert for Next and only leaks into whatever else reads the
file. `.env.example` shipped `NODE_ENV=production` for exactly this reason and it has been removed.

## Conventions

**Co-located with their subjects.** `nav-sidebar.test.tsx` sits next to `nav-sidebar.tsx`.

```
packages/components/src/layout/nav-sidebar.tsx
packages/components/src/layout/nav-sidebar.test.tsx
```

This deliberately diverges from `server/tests/`, which mirrors `app/` in a parallel tree. Files move
between packages here routinely — `SettingsDialog` was promoted from `apps/web` into
`packages/components` — and a co-located test rides along with `git mv`, while a parallel tree has to
be remembered. The one time it is not, you get an orphaned test importing a path that no longer
exists. Python's `tests/` convention exists partly for packaging reasons that do not apply to
workspace-internal TypeScript.

One consequence worth knowing: `@app/components` exports `"./*": "./src/*.tsx"`, so a co-located test
is nominally importable as `@app/components/layout/nav-sidebar.test`. Harmless — the package is
`private: true` and never builds — but it is real.

**`*.test.*` is Vitest. `*.spec.*` is Playwright.** Vitest's default `include` matches both, so
`vitest.config.mts` pins it to `.test.` only. E2E specs live in a top-level `e2e/` directory (they
have no package to co-locate with, since their subject is the running stack) and must never be run by
Vitest — they need a live server and a database.

**Formatting and lint.** New test files are checked by Prettier (`semi: false`) and, in `apps/web`,
`packages/ui`, `packages/components` and `packages/auth`, by ESLint.

## Tests that pin known-wrong behaviour

Some tests assert behaviour that is **known to be wrong**, so that a fix is what makes them change.
Those are recorded in [`web-app/docs/bugs.md`](../../../web-app/docs/bugs.md); a test asserting a bug
names the entry in a comment.

Before "fixing" a test that looks wrong, check whether it is one of these.
