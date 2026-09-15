# Spec — Typed API Client Codegen (OpenAPI → orval → TanStack Query)

**Purpose:** rebuild guide for the end-to-end contract pipeline that turns a FastAPI
OpenAPI spec into committed, type-safe TanStack Query hooks, TypeScript types, and Zod
schemas — plus the conventions for consuming them in a Next.js App Router app.

**Status:** extracted from this monorepo (working implementation). Written to be
transplanted into a fresh repo.

**Revised:** 2026-09-01, reconciled against a working implementation. Four of
the original recommendations were superseded; the rationale for each is
recorded in §9 (Known gotchas) below — §9.1 (response-envelope mismatch, solved
by a config flag instead of a mutator rewrite), §9.2 (the `query.useQuery` /
`query.useMutation` trap), §9.3 (array query params), and §9.4 (`clean: true`
deleting hand-written files).

**Scope placeholder:** this document uses `@acme` as the npm scope. Substitute your own.

---

## 1. Principle

> **The backend owns the API contract. The frontend never hand-writes API types.**

A single artifact — `server/openapi.json` — is the hand-off. Everything on the frontend
side of that file is generated and committed. Any hand-written type describing a request
or response body is a bug.

Resist a shared `types` package. Once generated types exist, the only hand-written
types left are pure UI concerns — navigation shape, theme tokens, a widget's own state —
and each belongs beside the component that consumes it, in the UI package. A types
package with no owner is where API mirrors quietly reappear: it looks like the natural
home for "the shape of an order", and nothing about its name says otherwise.

### Pipeline

```
FastAPI app
   │  app.openapi()
   ▼
server/openapi.json                    ← committed artifact, the contract boundary
   │                                     filters: e.g. exclude tag "streaming" (§3, §4.2)
   ├─ orval target 1 (react-query) ──► packages/api-client/src/generated/endpoints/<tag>/<tag>.ts
   │                                   packages/api-client/src/generated/types/*.ts
   └─ orval target 2 (zod) ─────────► packages/api-client/src/generated/zod/<tag>/<tag>.ts
   │
   ▼  scripts/postgen.mjs (post-process)
   barrels only — orval owns everything else under src/generated/
   │
   ▼
apps/* import  @acme/api-client/endpoints/<tag>
               @acme/api-client/types
               @acme/api-client/zod/<tag>
```

### The two commands

```bash
# 1. Backend — dump the spec
cd server && make export-openapi

# 2. Frontend — regenerate hooks, types, zod schemas
cd web-app && pnpm --filter @acme/api-client gen:api
```

**Rule: both outputs land in the same commit.** Splitting the spec export from the
regeneration across commits/PRs is the single most common way this setup breaks — a
frontend build compiles against a contract the backend no longer serves.

### Enforcing the rule: a drift-guard script

Prose is not a guardrail. Add a script at the repo root — `scripts/check-contract.sh` —
that re-runs both commands above and fails if anything moved:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ARTIFACTS=(server/openapi.json web-app/packages/api-client/src/generated)

make -C server export-openapi
pnpm --dir web-app --filter @acme/api-client gen:api

# --porcelain catches a newly generated file for a newly added endpoint too;
# a plain `git diff` would miss an untracked file.
if [ -n "$(git status --porcelain -- "${ARTIFACTS[@]}")" ]; then
  echo "FAIL: the committed contract artifacts are stale." >&2
  git --no-pager status --porcelain -- "${ARTIFACTS[@]}"
  exit 1
fi
echo "PASS: server/openapi.json and the generated client are up to date."
```

Expose it as `make check-contract` and run the same target from CI on every pull
request. The export needs no database, `.env` file, or secret, so the job requires
nothing configured beyond the toolchains themselves — install uv, pnpm, and Node, and
run the target.

Two CI-specific traps, both silent until a fresh runner hits them:

- **`uv sync --frozen` does not install a `test` (or any non-default) dependency
  group.** If `check-contract` is paired with a pytest-based contract test (§3), sync
  with `--group test` (or your project's equivalent) explicitly — the CI step fails
  importing `pytest` on a clean runner even though it works on every developer machine
  that has already run a full `uv sync` locally.
- **`pnpm/action-setup` needs an explicit `version:`** unless the workspace's root
  `package.json` declares a `packageManager` field. Without either, the action cannot
  infer which pnpm to install and the job fails before checkout finishes.

---

## 2. Repository layout

```
repo/
├── server/
│   ├── openapi.json                 # generated, COMMITTED
│   ├── Makefile                     # export-openapi target
│   └── scripts/export_openapi.py
└── web-app/                         # pnpm workspace root
    ├── pnpm-workspace.yaml
    ├── apps/
    │   └── <portal>/                # Next.js app
    │       ├── next.config.ts       # transpilePackages
    │       └── src/
    │           ├── app/layout.tsx   # provider wiring
    │           ├── providers/
    │           │   └── query-provider.tsx
    │           ├── hooks/api/       # app-level mutation wrappers
    │           └── lib/zod-config.ts
    └── packages/
        └── api-client/
            ├── orval.config.ts
            ├── package.json
            ├── tsconfig.json
            ├── scripts/postgen.mjs
            └── src/
                ├── index.ts          # HAND-WRITTEN
                ├── use-api-fetch.ts  # HAND-WRITTEN — the mutator
                └── generated/        # GENERATED — orval owns this whole tree
                    ├── endpoints/    # tags-split
                    ├── types/        # flat
                    └── zod/          # tags-split
```

Only `src/index.ts` and `src/use-api-fetch.ts` are hand-written. Everything under
`src/generated/` is regenerated and must never be edited by hand. Putting every
generated directory under one parent, rather than as siblings of the hand-written files,
makes that structurally visible instead of a warning buried in prose (§9.4).

---

## 3. Backend — spec export

### `server/scripts/export_openapi.py`

```python
#!/usr/bin/env python3
"""Export the FastAPI OpenAPI spec to server/openapi.json.

FastAPI builds the spec from registered routes and Pydantic models via
`app.openapi()`, so no running server, network, or database is required —
only an environment that lets `from app.main import app` import cleanly.
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> int:
    output_path = Path(__file__).resolve().parent.parent / "openapi.json"
    spec = app.openapi()

    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(spec, fp, indent=2, sort_keys=True)
        fp.write("\n")

    print(f"Wrote OpenAPI spec to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `server/Makefile`

```make
export-openapi:
	@echo "Exporting OpenAPI spec to server/openapi.json"
	@APP_ENV=$${APP_ENV:-development} PYTHONPATH=. uv run python scripts/export_openapi.py
```

### Requirements on the export

| Requirement | Why |
|---|---|
| `indent=2, sort_keys=True` | Deterministic output. Without sorting, dict ordering churn produces enormous meaningless diffs and defeats review. |
| No server/DB needed | Export must be runnable in CI and pre-commit, offline. Keep `app.main` import side-effect-free (no eager DB connection at import time). |
| Every router has an explicit `tags=[...]` | Tags become the generated directory names and the module boundaries of the client. Untagged routes collapse into a `default` bucket. |
| Every route has a stable `operation_id` (or a unique function name) | The operation id becomes the hook name (`list_suppliers` → `useListSuppliers`). Renaming a handler renames a public frontend symbol. |
| Response models declared on every route | A route without `response_model` generates `unknown` and silently erases type safety. `Dict[str, Any]` does **not** satisfy this — see below. |

**`Dict[str, Any]` is not a response model.** FastAPI happily accepts it as a return-type
annotation, but it emits `additionalProperties: true` in the schema, and orval generates
`{[key: string]: unknown}` from that — the client still compiles, but every field access
on the response is now `unknown`. If a route's shape is genuinely open-ended, that is a
signal to model it (even a `dict[str, SomeEnum]` is a real improvement), not a reason to
reach for `Any`.

**Casing is a project convention, not an orval requirement.** Pick one (camelCase,
snake_case, …) and enforce it — orval does not care, but a mixed client does not read as
one API. This guide's examples use snake_case operation ids for illustration
(`list_suppliers` → `useListSuppliers`); the reference implementation this guide was
extracted from uses camelCase (`getMe`, `listConversations`) instead. Either is fine as
long as it is consistent and, ideally, enforced by the test in the next section.

**Two further rules, easy to miss because nothing in FastAPI enforces them:**

- **Streaming / SSE routes** have no JSON body to declare, so they cannot satisfy the
  response-model rule and should not be forced to. Give the route its own tag (e.g.
  `tags=["streaming"]`) and exclude that tag on the frontend side with orval's
  `input.filters` (§4.2), rather than special-casing the route in the export itself. It
  stays visible in Swagger; it simply never reaches the generated client.

  A route-level `tags=[...]` does **not replace** the tags its router was
  `include_router`-ed with — it merges. A streaming route on a router included with
  `tags=["chatbot"]` that itself declares `tags=["streaming"]` ends up tagged
  `["chatbot", "streaming"]` in the emitted schema, not `["streaming"]` alone. That is
  harmless for the exclusion above: orval's tag filter is membership-based
  (`operation.tags.some(tag => filterTags.some(...))`, verified against `@orval/core`
  8.27.0's `input-filters.ts`), so an operation carrying the excluded tag anywhere in its
  tag list is dropped regardless of what else it is tagged with. Worth stating
  explicitly — a reader who notices the merge and doesn't know this will assume the
  exclusion is broken and go looking for a bug that isn't there.

- **Server-to-server routes** (webhook receivers, anything meant only for
  infrastructure) declare `include_in_schema=False`. They never enter the OpenAPI
  document at all, so the frontend can never get a hook for one — a stronger guarantee
  than a tag filter, and the right choice whenever a route has no legitimate reason to
  appear in Swagger either.

**Naming contract:** `operation_id` is a public API of the frontend. Treat renames as
breaking changes.

### Enforcing this table mechanically

The rules above are easy to state and easy to forget under deadline pressure. Write a
test directly against `app.openapi()` — no database, no running server — that fails when
any operation violates one of them: a missing tag, a missing or off-convention
`operation_id`, a duplicate `operation_id`, a 2xx response with no schema and no `204`.

**One assertion is a trap.** Checking for the presence of a `content` key on the
response object does not detect an untyped route. FastAPI emits
`content: {"application/json": {"schema": {}}}` for *any* route with no
`response_model` — the key is always there, empty schema and all — so a test written as
`"content" in response` passes for exactly the routes it exists to catch. Assert that
the 2xx response's JSON **schema is non-empty**
(`response["content"]["application/json"]["schema"] != {}`), not merely that the
`content` key exists.

---

## 4. Frontend — the `api-client` package

### 4.1 `package.json`

```json
{
  "name": "@acme/api-client",
  "version": "0.0.1",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts",
    "./endpoints/*": "./src/generated/endpoints/*/index.ts",
    "./types": "./src/generated/types/index.ts",
    "./zod/*": "./src/generated/zod/*/index.ts"
  },
  "scripts": {
    "gen:api": "orval && node scripts/postgen.mjs",
    "build": "tsc -b",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "@acme/auth": "workspace:*",
    "@tanstack/react-query": "^5.99.2",
    "zod": "^4.0.0"
  },
  "peerDependencies": {
    "react": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.2.14",
    "orval": "8.27.0",
    "prettier": "3.9.6",
    "typescript": "^5.9.3"
  }
}
```

Notes:

- The package ships **raw TypeScript source** (`main` → `src/index.ts`), not a build
  output. This requires `transpilePackages` in each consuming Next.js app (§6.3). It
  removes a build step from the inner loop; the trade-off is that non-Next consumers
  would need their own transpile config.
- The wildcard `exports` subpaths are what make per-tag imports work
  (`@acme/api-client/endpoints/orders`). They resolve to the per-tag barrels that
  `postgen.mjs` writes under `src/generated/` (§5).
- `react` is a **peer** dependency — the package must never bundle its own React copy.
- **Pin `orval` and `prettier` to exact versions, not a caret range.** The tree under
  `src/generated/` is committed to version control; a caret lets a routine
  `pnpm install` bump orval and silently rewrite hundreds of tracked files with no
  commit message explaining why. `prettier` needs the same treatment, since its
  formatting is baked into that committed output. This guide's snippets were last
  verified against orval `8.27.0` specifically — the option names referenced throughout
  (`formatter`, `override.fetch.includeHttpResponseReturnType`, the mutator-detection
  rule in §6.1) are 8.x. orval 7.x used different option names; if you are starting from
  a 7.x install, check the changelog before copying these snippets verbatim.
- **`prettier` must be an explicit `devDependency` of this package**, not merely present
  somewhere else in the workspace. orval's formatter option shells out to a local
  binary; if this package doesn't declare its own copy, a strict/isolated install (or a
  future extraction of this package on its own) has nothing to find.
- **If the workspace restricts postinstall scripts** (pnpm's `allowBuilds`, or the older
  `onlyBuiltDependencies`), add `esbuild` to the allowlist. `@orval/core` depends on it
  to compile a TypeScript `orval.config.ts` at generation time — without it,
  `pnpm install` succeeds but `orval` fails outright the first time anyone runs
  `gen:api`.

### 4.2 `orval.config.ts`

Two targets read the same spec:

```ts
import { defineConfig } from "orval"

// Both targets read the same committed artifact.
const input = {
  target: "../../../server/openapi.json",
  // Exclude SSE/streaming routes: they have no JSON response schema (§3), and
  // generating a react-query mutation for one produces a hook that returns
  // `unknown` and that nobody should call.
  filters: { mode: "exclude" as const, tags: ["streaming"] },
}

export default defineConfig({
  acmeApi: {
    input,
    output: {
      mode: "tags-split",
      target: "./src/generated/endpoints",
      schemas: "./src/generated/types",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      // orval 8.x calls this `formatter`, not `prettier`. `prettier: true` —
      // the option name many older examples still show — is not a valid
      // OutputOptions key in 8.x. It is silently ignored, and the generated
      // tree comes out unformatted with no error telling you why.
      formatter: "prettier",
      override: {
        // Makes the generated types resolve the parsed body directly instead
        // of an { data, status, headers } envelope. See §9.1 — without this,
        // every call site needs `as unknown as T`.
        fetch: { includeHttpResponseReturnType: false },
        // A `use`-prefixed name makes orval call the mutator INSIDE each
        // generated hook, rather than importing it as a plain function. That
        // is what removes the need for a module-level client singleton and a
        // provider to initialise it — see §6.1.
        mutator: {
          path: "./src/use-api-fetch.ts",
          name: "useApiFetch",
        },
        // Deliberately no `query: { useQuery, useMutation }` here — see §9.2.
      },
    },
  },
  acmeZod: {
    input,
    output: {
      mode: "tags-split",
      target: "./src/generated/zod",
      client: "zod",
      clean: true,
      formatter: "prettier",
    },
  },
})
```

| Option | Effect / rationale |
|---|---|
| `mode: "tags-split"` | One directory per OpenAPI tag, each with `<tag>.ts`. Keeps generated files reviewable and makes per-feature imports possible. |
| `schemas: "./src/generated/types"` | Schema models emitted **flat**, one file per schema, shared by both targets' consumers. |
| `client: "react-query"` | Emits `useX` query/mutation hooks plus `getXQueryKey` / `getXUrl` and related helpers. |
| `httpClient: "fetch"` | No axios dependency. Pairs with the custom mutator. |
| `clean: true` | Wipes target dirs before writing — stale hooks from deleted endpoints cannot survive. **This is why the postgen script must run after every generation (§5).** |
| `filters: { mode: "exclude", tags: [...] }` | Drops any operation carrying a listed tag from generation entirely, regardless of what other tags it also carries (§3). |
| `formatter: "prettier"` | The correct 8.x key for output formatting. `prettier: true`, the option many 7.x-era examples show, is silently ignored in 8.x. |
| `override.fetch.includeHttpResponseReturnType: false` | Generated types resolve the body directly, matching what a hook mutator returns. See §9.1. |
| `override.mutator` | Every generated call routes through `useApiFetch` instead of raw `fetch`, so auth/base-URL/error handling live in one hand-written file. Because the name is `use`-prefixed, orval calls it as a hook — see §6.1. |

### 4.3 Generated surface (per tag)

For a `suppliers` tag with a `list_suppliers` operation, orval emits into
`src/generated/endpoints/suppliers/suppliers.ts`:

- `getListSuppliersUrl(params)` — URL + query-string builder (a plain function)
- `useListSuppliersHook()` — a hook returning the bare fetcher bound to the current
  mutator. Because the mutator is hook-shaped (§6.1), this is a hook too — it cannot be
  called outside a component render, which is the trade-off discussed there.
- `getListSuppliersQueryKey(params)` — `['/api/v1/suppliers', params?]` (a plain
  function — a cache key needs no auth context, so this export stays callable anywhere)
- `useListSuppliersQueryOptions(params, options)` — composable options object, also
  hook-shaped for the same reason as `useListSuppliersHook`
- `useListSuppliers(params, options)` — the hook
- Response/param types: `ListSuppliersParams`, `listSuppliersResponse200`, …

Mutations get `useCreateSupplier(options)` with an orval-shaped options bag —
`{ mutation: UseMutationOptions, request: RequestInit }` — plus the mutation-side
equivalents `getCreateSupplierMutationKey()` (plain function) and
`useCreateSupplierMutationOptions()` (hook).

**The `getXQueryKey` / `getXMutationKey` helpers are the backbone of cache invalidation
(§6.4, §7). Never hand-write a query key string** — and note that, unlike most of this
tag's other exports, they stay plain functions: a cache key is a pure function of its
params and needs no mutator, so it is callable from anywhere.

---

## 5. The post-processing script

`clean: true` deletes anything orval did not itself emit, so the barrel `index.ts` files
under `src/generated/` must be regenerated after every run.

### `packages/api-client/scripts/postgen.mjs`

```js
#!/usr/bin/env node
// Regenerate the barrel index.ts files under src/generated/.
//
// orval's `clean: true` wipes these directories on every run, so this must run
// immediately after `orval` — wired into the `gen:api` npm script (§4.1).
//
// One Node file, not a shell script wrapping a heredoc'd Node program (a shape
// this guide used to recommend): a template repo gets cloned onto machines
// without bash, and that shape does not run on Windows.
//
// - endpoints/ and zod/ use tags-split layout: one subdirectory per OpenAPI
//   tag, each holding <tag>.ts. Each tag gets its own index.ts — that is what
//   the "./endpoints/*" and "./zod/*" subpath exports in package.json resolve
//   to — plus one barrel over all tags.
// - types/ is flat: one .ts per schema, with a single barrel over all of them.

import { existsSync, readdirSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "..")
const generated = join(packageRoot, "src", "generated")

let written = 0

for (const area of ["endpoints", "zod"]) {
  const dir = join(generated, area)
  if (!existsSync(dir)) continue

  const tags = readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort()

  for (const tag of tags) {
    writeFileSync(join(dir, tag, "index.ts"), `export * from "./${tag}"\n`)
    written++
  }
  writeFileSync(join(dir, "index.ts"), tags.map((t) => `export * from "./${t}/${t}"\n`).join(""))
  written++
}

const typesDir = join(generated, "types")
if (existsSync(typesDir)) {
  const modules = readdirSync(typesDir)
    .filter((f) => f.endsWith(".ts") && f !== "index.ts")
    .map((f) => f.slice(0, -3))
    .sort()
  writeFileSync(join(typesDir, "index.ts"), modules.map((m) => `export * from "./${m}"\n`).join(""))
  written++
}

// A silent no-op is worse than a failure here. Both loops above skip missing
// directories, so a failed generation — or an `input.filters` that matched
// every operation out of both targets — would otherwise leave this script
// printing success over an empty package. A CI drift guard built on `gen:api`
// (§1) would then report green over a broken tree.
if (written === 0) {
  console.error(
    `postgen: wrote no barrel files. Expected generated output under ${generated}.\n` +
      "Either orval did not run, or every operation was filtered out of both targets.",
  )
  process.exit(1)
}

console.log(`postgen: wrote ${written} barrel file(s)`)
```

Wired into `package.json` as `"gen:api": "orval && node scripts/postgen.mjs"` (§4.1).

A generator bug in orval's array-query-parameter serialization used to be patched here
too, as a regex over this script's output. It is not something every project needs —
see §9.3 for when (and whether) to add it.

---

## 6. Runtime wiring

### 6.1 The mutator — `src/use-api-fetch.ts` (hand-written)

The single point where auth, base URL, and error normalization live. It is a **hook**,
not a module-level singleton — orval recognises the `use`-prefixed name it is configured
with (§4.2) and calls it inside each generated hook, so it reads the current auth
context on every call rather than once at module load. No provider, no module-level
client, no "call this before you use anything" ordering requirement.

```ts
import { useCallback } from "react"
import { useAppAuth } from "@acme/auth"

/**
 * The single error type the application layer needs to know about.
 *
 * `requestId` is the server's correlation id, read from the X-Request-ID
 * response header. FastAPI's CorrelationIdMiddleware stamps every request and
 * binds the id to the server's structured logs, so a client-side failure stays
 * traceable to a server log line without the response body ever being shown to
 * a user.
 */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  readonly requestId: string | null

  constructor(message: string, status: number, body: unknown, requestId: string | null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
    this.requestId = requestId
  }
}

/**
 * The error type orval wires into every generated hook's `TError`.
 *
 * orval scans this file's text for the literal `export type ErrorType` and,
 * finding it, emits `ErrorType<...>` in place of the error type it would
 * otherwise derive from the spec's declared error response. Without this,
 * every hook advertises an error it cannot produce (e.g. a 422's declared
 * validation-error schema), while the mutator below only ever throws
 * `ApiError`. The body generic is accepted and ignored on purpose — nothing
 * validates the thrown error's body against a declared schema, so typing it
 * more precisely would just relocate the lie rather than remove it.
 */
export type ErrorType<_Body = unknown> = ApiError

function resolveBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL
  if (!url) throw new Error("@acme/api-client: NEXT_PUBLIC_API_URL is not set")
  return url.replace(/\/+$/, "")
}

async function parseErrorBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? ""
  try {
    if (contentType.includes("application/json")) return await response.json()
    return await response.text()
  } catch {
    return null
  }
}

export function useApiFetch() {
  const { getToken } = useAppAuth()

  return useCallback(
    async <T>(url: string, init?: RequestInit): Promise<T> => {
      const fullUrl = /^https?:\/\//i.test(url) ? url : `${resolveBaseUrl()}${url}`
      const headers = new Headers(init?.headers)

      const token = await getToken()
      if (token && !headers.has("authorization")) {
        headers.set("Authorization", `Bearer ${token}`)
      }

      // Only set JSON content-type for plain bodies — never for FormData
      // (the browser must set its own multipart boundary), Blob, or ArrayBuffer.
      const body = init?.body
      if (
        body != null &&
        !headers.has("content-type") &&
        !(body instanceof FormData) &&
        !(body instanceof Blob) &&
        !(body instanceof ArrayBuffer)
      ) {
        headers.set("Content-Type", "application/json")
      }

      const response = await fetch(fullUrl, { ...init, headers })
      const requestId = response.headers.get("x-request-id")

      if (!response.ok) {
        // Deliberately not response.statusText: the reason phrase is
        // server-supplied text, and server error text must never reach the UI.
        // status, body and requestId still carry everything needed to debug.
        throw new ApiError(
          `HTTP ${response.status}`,
          response.status,
          await parseErrorBody(response),
          requestId,
        )
      }

      if (response.status === 204) return undefined as T
      if (response.headers.get("content-length") === "0") return undefined as T

      const contentType = response.headers.get("content-type") ?? ""
      if (contentType.includes("application/json")) return (await response.json()) as T

      return (await response.text()) as unknown as T
    },
    [getToken],
  )
}
```

Responsibilities, in order:
1. Prefix relative URLs with `baseUrl` (absolute URLs pass through untouched).
2. Attach `Authorization: Bearer <token>` unless the caller already set one.
3. Set `Content-Type: application/json` only for plain bodies.
4. Throw `ApiError(status, body, requestId)` on any non-2xx — **this is the only error
   type the app layer needs to know about**, and exporting `ErrorType` (above) is what
   makes every generated hook's declared error type agree with that at compile time too.
   The message is `HTTP <status>`, never `response.statusText` and never the body: the
   reason phrase is text the server chose, and §6.4 maps a *status* to curated copy
   precisely so no server-authored string can be rendered.
5. Return `undefined` for 204 / zero-length; parse JSON; fall back to text.

**Trade-off.** Because `useApiFetch` is a hook, everything orval generates against this
mutator — including the bare fetcher (§4.3's `useXHook`) — can only be called from
inside a React component. A call site outside React (an RSC prefetch, a route handler, a
plain script) needs its own hand-written path: plain `fetch` plus the generated Zod
schema is the same pattern §6.6 already uses for unauthenticated routes, and it composes
for authenticated ones too, given a token from wherever that context lives server-side.
If out-of-React calls are common in your app, consider the alternative below instead.

### Alternative: a module-level singleton

Projects that need to call generated endpoints outside a component — an RSC data-fetch,
a server action, a background job, as a matter of course rather than an exception — can
still route through orval's fetch client with a plain, non-hook mutator. Set
`override.mutator.name` to something **not** `use`-prefixed (`customInstance`, in the
example below) and orval imports it as an ordinary function instead of calling it inside
each hook. The mutator then needs an explicit initialisation step, since it can no
longer reach into React context for a token:

```ts
// src/custom-instance.ts — hand-written, the singleton alternative
export type GetToken = () => Promise<string | null> | string | null

export interface CreateApiClientOptions {
  getToken: GetToken
  baseUrl: string
}

type Mutator = <T>(url: string, init?: RequestInit) => Promise<T>

let _instance: Mutator | null = null

export function createApiClient(options: CreateApiClientOptions): Mutator {
  const { getToken, baseUrl } = options
  // ... same fetch/auth/error body as useApiFetch (§6.1), minus the hook
  // plumbing: no useCallback, and getToken/baseUrl come from the closure
  // captured here instead of from a hook call on every render.
  const mutator: Mutator = async <T>(url: string, init?: RequestInit): Promise<T> => { /* ... */ }
  _instance = mutator
  return mutator
}

/** Module-level mutator referenced by every generated endpoint. */
export const customInstance: Mutator = <T>(url: string, init?: RequestInit): Promise<T> => {
  if (!_instance) {
    throw new Error(
      "customInstance: createApiClient(...) must be called before using generated endpoints",
    )
  }
  return _instance<T>(url, init)
}
```

Something — usually a thin `ApiClientProvider` — must call `createApiClient(...)` before
any generated call fires. That ordering is load-bearing: a `useEffect` races the first
render's query, so the call has to happen synchronously in the render body, guarded so
it runs exactly once (a `useRef` flag is the usual shape), *before* any child mounts.
This is strictly more machinery than the hook mutator removes, and in a Next.js
server process a module-scope `_instance` is shared across concurrent requests — one
user's token can serve another user's request unless every call site is careful to
reconfigure it first.

**Default to the hook mutator in §6.1.** Reach for `createApiClient` / `customInstance`
only when out-of-React calls are common enough that hand-writing a fetcher per call site
(§6.6's pattern) stops paying for itself.

### 6.2 `src/index.ts` (hand-written)

The package's public runtime surface is deliberately tiny:

```ts
export { ApiError, useApiFetch } from "./use-api-fetch"
```

Everything else is reached through the subpath exports so that importing one tag does
not pull in the whole client.

### 6.3 Provider wiring

There is no `ApiClientProvider`, and no ordering requirement beyond the one React
already enforces: whatever supplies `useAppAuth()` must sit above anything that issues a
query, so `useApiFetch` can read a token when a generated hook calls it.

```tsx
<AuthProvider>          {/* provides useAppAuth() / getToken            */}
  <QueryProvider>       {/* QueryClient + global error → toast, §6.4    */}
    <ThemeProvider>
      {children}
      <Toaster />
    </ThemeProvider>
  </QueryProvider>
</AuthProvider>
```

`next.config.ts` must still transpile the workspace packages, since they ship raw TS:

```ts
transpilePackages: ["@acme/ui", "@acme/auth", "@acme/api-client"]
```

### 6.4 `QueryProvider` — defaults and centralized error → toast

```tsx
"use client"

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { useState } from "react"
import { toast } from "sonner"
import { ApiError } from "@acme/api-client"
import { messages } from "@/lib/messages"

/**
 * SECURITY: never surface `err.message` or `err.body` — server payloads
 * may contain stack traces or internal route names. Map status → curated copy.
 */
function mapErrorToToast(err: unknown): void {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401: toast.error(messages.toasts.sessionExpired); return
      case 403: toast.error(messages.toasts.forbidden);      return
      case 404: toast.error(messages.toasts.notFound);       return
      case 409: toast.error(messages.toasts.conflictError);  return
      case 422: toast.error(messages.toasts.validationError);return
      default:  toast.error(messages.toasts.genericError);   return
    }
  }
  toast.error(messages.toasts.genericError)
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (err, query) => {
            // onError fires for background refetches too. A poll that fails
            // every 30s would otherwise toast every 30s behind data the user
            // can already see — only a query that has never resolved toasts,
            // and any query can opt out entirely via its own `meta`.
            if (query.meta?.silentError === true) return
            if (query.state.data !== undefined) return
            mapErrorToToast(err)
          },
        }),
        // Mutations always toast: the user just acted and is waiting for a result.
        mutationCache: new MutationCache({ onError: mapErrorToToast }),
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            gcTime: 5 * 60 * 1000,
            refetchOnWindowFocus: false,
            // Retrying a 4xx burns a request on an answer that will not change.
            retry: (failureCount, err) =>
              failureCount < 1 && !(err instanceof ApiError && err.status < 500),
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}
```

Consequences to design around:

- **`QueryClient` is created inside `useState`,** never at module scope. A module-scope
  client is shared across requests on the server and leaks one user's cache into
  another's.
- **Error toasts are global.** Feature code must NOT add a generic `onError` toast to an
  individual mutation — that double-toasts. Per-mutation `onError` is reserved for
  *specific* handling (field-level errors, rollback).
- **Query error toasts are gated on first load.** `onError` fires for background
  refetches too, not just the initial fetch — a polling query that fails repeatedly
  would otherwise toast on every failed poll, behind data the user can already see and
  trust. Toast only when `query.state.data === undefined`; a query can also opt out
  entirely with `meta: { silentError: true }`, for a widget that already renders its own
  degraded/offline state.
- **4xx is not retried.** A validation error or a 404 will not change on retry; `retry`
  becomes a predicate so only 5xx spends a second request.
- **Keep the devtools**, gated on environment. They cost nothing once gated behind a
  dev-only check and are usually the fastest way to see why a query did or didn't
  refire — don't drop them to trim the provider.
- **Never echo server error text.** Status → curated copy only.

### 6.5 Reading data — query hooks

Import from the per-tag subpath, not the package root:

```tsx
"use client"

import { useListSuppliers } from "@acme/api-client/endpoints/suppliers"
import type { SupplierListItem } from "@acme/api-client/types"

export function SupplierList() {
  const { data, isPending } = useListSuppliers(queryArgs)

  // No cast: includeHttpResponseReturnType: false (§4.2, §9.1) makes `data`
  // resolve to the parsed body's type directly.
  const items: SupplierListItem[] = data?.items ?? []
  // ...
}
```

Conventions:
- Filter/sort/pagination state lives in the URL, read by a small `useXFilters()` hook that
  returns a `queryArgs` object passed straight to the generated hook. The generated
  `getXQueryKey(params)` includes `params`, so a filter change is automatically a distinct
  cache entry.
- Use `isPending` for first load; render a skeleton, not a spinner-on-empty-table.

### 6.6 Unauthenticated / server-side routes

Public routes must not go through the generated hooks at all — the mutator is hook-shaped
(§6.1), so even its bare fetcher only runs inside a component, and a public route in
particular has no reason to carry a bearer token. Use plain `fetch` plus the generated
Zod schema to validate the response — the same pattern that answers §6.1's out-of-React
trade-off for authenticated routes too, given a token from wherever that context lives
outside React:

```ts
import { getPublicPackageResponse } from "@acme/api-client/zod/public-packages"
import type { PublicPackageResponse } from "@acme/api-client/types"

export class PublicPackageError extends Error {
  readonly status: number
  constructor(status: number) {
    super(`public_package_${status}`)
    this.name = "PublicPackageError"
    this.status = status
  }
}

export async function fetchPublicPackage(token: string, signal?: AbortSignal) {
  const base = process.env.NEXT_PUBLIC_API_URL
  if (!base) throw new PublicPackageError(0)   // status 0 = misconfiguration; never leak detail

  const res = await fetch(`${base}/public/packages/${encodeURIComponent(token)}`, {
    method: "GET",
    signal,
    headers: { Accept: "application/json" },
    cache: "no-store",
  })
  if (!res.ok) throw new PublicPackageError(res.status)

  // Contract drift surfaces as a parse error → same generic error UI.
  return getPublicPackageResponse.parse(await res.json()) as PublicPackageResponse
}
```

This is the main payoff of generating the Zod target: **runtime contract validation at the
trust boundary**, using the same source of truth as the types. Also keep the public route
tree out of the auth providers entirely, so no auth SDK mounts above it.

---

## 7. App-level wrapper hooks (`src/hooks/api/`)

Generated mutation hooks know nothing about your cache graph. Wrap each one **once**, in
the app, and export it from a barrel. Feature components import the wrapper, never the
generated mutation directly.

Rules:
- One file per mutation: `use-create-supplier.ts`.
- The wrapper owns cache invalidation and optimistic updates.
- The wrapper never toasts generic errors (the `MutationCache` does).
- Query keys always come from generated `getXQueryKey()` helpers.

### 7.1 Simple case — invalidate on success

Use this whenever the server generates values the client cannot predict (ids, tokens,
computed status). Do **not** attempt an optimistic insert there.

```ts
import {
  useCreateSupplier as useGenerated,
  getListSuppliersQueryKey,
} from "@acme/api-client/endpoints/suppliers"
import { useQueryClient } from "@tanstack/react-query"

export function useCreateSupplier() {
  const qc = useQueryClient()
  return useGenerated({
    mutation: {
      onSuccess: () => qc.invalidateQueries({ queryKey: getListSuppliersQueryKey() }),
    },
  })
}
```

### 7.2 Optimistic case — the canonical lifecycle

Use only for row-level edits whose result the client can predict exactly.

```ts
import {
  useApproveDocument as useGenerated,
  getListOrderDocumentsQueryKey,
} from "@acme/api-client/endpoints/documents"
import { getGetOrderQueryKey } from "@acme/api-client/endpoints/orders"
import type { DocumentListItem } from "@acme/api-client/types"
import { useQueryClient } from "@tanstack/react-query"

export function useApproveDocument(orderId: string) {
  const qc = useQueryClient()
  return useGenerated({
    mutation: {
      onMutate: async ({ docId }: { docId: string }) => {
        const docsKey = getListOrderDocumentsQueryKey(orderId)
        await qc.cancelQueries({ queryKey: docsKey })          // 1. stop in-flight refetches
        const prev = qc.getQueryData<DocumentListItem[]>(docsKey) // 2. snapshot
        if (prev) {
          qc.setQueryData<DocumentListItem[]>(                  // 3. apply predicted state
            docsKey,
            prev.map((d) => (d.id === docId ? { ...d, status: "APPROVED" } : d)),
          )
        }
        return { prev }                                        // 4. hand snapshot to onError
      },
      onError: (_err, _vars, ctx) => {
        const previous = (ctx as { prev?: DocumentListItem[] } | undefined)?.prev
        if (previous) qc.setQueryData(getListOrderDocumentsQueryKey(orderId), previous)
      },
      onSettled: () => {
        // Invalidate BOTH the edited list and any rollup that derives from it.
        qc.invalidateQueries({ queryKey: getListOrderDocumentsQueryKey(orderId) })
        qc.invalidateQueries({ queryKey: getGetOrderQueryKey(orderId) })
      },
    },
  })
}
```

`cancelQueries → snapshot → setQueryData → return ctx → rollback on error → invalidate on
settled`. Deviating from this order reintroduces the classic races (an in-flight refetch
overwriting the optimistic state; a rollback to a snapshot taken after the write).

**Decision rule:**

| Situation | Strategy |
|---|---|
| Server generates id / token / timestamp | Invalidate on success. No optimistic. |
| Server derives cascading state (status transitions, rollups) | Invalidate on success. No optimistic. |
| Row-level field edit with a fully predictable result | Optimistic + rollback + invalidate on settled. |

Always invalidate **derived** queries too — a document status change also moves the parent
order's completion percentage.

---

## 8. Forms — generated Zod schemas + React Hook Form

Orval's Zod target emits a schema per request body, named after the operation:
`createSupplierBody`, `updateSupplierBody`, `inviteSupplierContactBody`.

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { FormProvider, useForm, type Resolver } from "react-hook-form"
import { z } from "zod"

import { ApiError } from "@acme/api-client"
import type { SupplierCreate } from "@acme/api-client/types"
import { createSupplierBody } from "@acme/api-client/zod/suppliers"
import { useCreateSupplier } from "@/hooks/api"

// Extend, never replace: client-only fields are added on top of the generated schema
// so server-side constraints stay authoritative and regenerate automatically.
const formSchema = createSupplierBody.extend({
  contact_email: z.string().email().optional().or(z.literal("")),
})

export function NewSupplierModal() {
  const form = useForm<CreateSupplierFormValues>({
    resolver: zodResolver(formSchema) as unknown as Resolver<CreateSupplierFormValues>,
    mode: "onBlur",
    defaultValues: DEFAULT_VALUES,
  })

  const create = useCreateSupplier()

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await create.mutateAsync({ data: toPayload(values) })
    } catch (err) {
      // Field-level errors are handled here; the generic toast comes from MutationCache.
      if (err instanceof ApiError && err.status === 409) {
        const body = err.body as { field?: string } | undefined
        form.setError(body?.field === "vat_number" ? "vat_number" : "code", {
          type: "conflict",
          message: messages.suppliers.modal.create.codeConflict,
        })
      }
      return
    }
    // success path…
  })
}
```

Rules:
- **Extend the generated schema; never re-declare it.** A client-only field is `.extend()`;
  a hand-written duplicate of a server constraint will drift.
- **Strip client-only fields before building the request payload** — the generated request
  type is the contract.
- **409 / field-specific errors** → `form.setError` on the field the server names. Fall
  back to a sensible default field when the API does not yet return a `field` hint.
- **Every other error** falls through to the global `MutationCache` toast. Do not add a
  second one.
- Use `mode: "onBlur"` so validation fires on leaving a field, not on every keystroke.

### Localized validation messages

Install a global Zod error map once, as a bare side-effect import at the top of the root
layout, so generated *and* hand-written schemas render localized messages:

```ts
// src/lib/zod-config.ts — no exports; runs at module evaluation
import { z } from "zod"

z.config({
  customError: (issue) => {
    switch (issue.code) {
      case "invalid_type":   return "Valore non valido."
      case "too_small":      return issue.origin === "string"
        ? `Troppo corto (min ${issue.minimum} caratteri).`
        : "Valore troppo piccolo."
      case "invalid_format": return issue.format === "email" ? "Email non valida." : "Formato non valido."
      default:               return "Campo non valido."
    }
  },
})
```

Imported as `import "@/lib/zod-config"` on the **first line** of `app/layout.tsx`, before
any schema is evaluated.

---

## 9. Known gotchas

### 9.1 The response-envelope mismatch — solved by a config flag

Orval's **fetch** client, by default, types every response as an envelope:

```ts
export type listSuppliersResponse200 = { data: PaginatedResponseSupplierListItem; status: 200 }
export type listSuppliersResponseSuccess = listSuppliersResponse200 & { headers: Headers }
export type listSuppliersResponse = listSuppliersResponseSuccess | listSuppliersResponseError
```

If your mutator resolves and returns the parsed body directly — as `useApiFetch` does
(§6.1) — the declared type and the runtime value disagree, which forces a cast at every
call site: `data as unknown as PaginatedResponseSupplierListItem`. That is exactly the
kind of hand-maintained type-shape knowledge this guide's principle (§1) says should
never exist on the frontend.

There is no design decision to make here: set the flag that makes the generated types
match what the mutator actually returns.

```ts
override: {
  fetch: { includeHttpResponseReturnType: false },
}
```

Zero casts anywhere, no `unwrap<T>()` helper to remember to reach for, no mutator
rewrite. See §4.2 for the config in context and §6.5 for a call site with the cast
already gone.

### 9.2 The `query.useQuery` / `query.useMutation` trap (the dangerous one)

It's tempting to set `override.query.useQuery: true` and `override.query.useMutation:
true` on the react-query target, reading them as "generate both a query hook and a
mutation hook for every operation." **They are not that.** They are global forces that
override orval's per-verb default, and orval then breaks the resulting tie by demoting
whichever kind lost — `if (GET && isMutation) isQuery = false`, and the converse for
non-GET (verified against `@orval/query` 8.27.0's resolution logic). Set both to `true`
and the tie breaks the *same* way regardless of verb, which inverts every operation:
every `GET` becomes a mutation, and every non-GET becomes a query.

Concretely, that turns a `DELETE /me`-style operation into `useDeleteMe` typed as a
`useQuery` — a hook that fires automatically on component mount and refetches on window
focus. An account-deletion call wired to render. The code compiles, the hook name looks
completely ordinary, and nothing about it announces itself as a mutation-shaped bomb
until it actually fires.

**Omit both flags.** orval's default is already `useQuery = (verb === GET)` /
`useMutation = (verb !== GET)` — precisely the desired behavior — so the correct config
is to not touch this option at all (§4.2).

### 9.3 Array query params — a hazard to watch for, not code to ship pre-emptively

orval's fetch client has, in past versions, serialized an array-valued query parameter
with `value.toString()`, producing `?status=A,B` instead of the repeated-key form
(`?status=A&status=B`) most backends expect. Against a FastAPI `list[T] = Query(...)`
parameter, the server sees one comma-joined string and either 422s on enum validation or
matches nothing. **The failure is silent from the frontend's perspective** — no type
error, no exception, just empty or unexpected results.

Don't carry a fix into a fresh project pre-emptively. Check whether your orval version
reproduces this, against an endpoint that actually takes an array query parameter,
before writing any code for it. If it does, and you have such an endpoint, patch it as a
regex over generated output, run every time `postgen.mjs` runs (§5), so it survives
`clean: true`:

```js
// Rewrite every generated forEach body to branch on Array.isArray and repeat
// the key, instead of joining the array into one comma-separated value.
// Idempotent: a second run finds no matches and writes nothing.
const broken = /if \(value !== undefined\) \{\s*\n\s*normalizedParams\.append\(key, value === null \? 'null' : value\.toString\(\)\)\s*\n\s*\}/g
const fixed =
  "if (value === undefined) return\n" +
  "    if (Array.isArray(value)) {\n" +
  "      for (const item of value) {\n" +
  "        normalizedParams.append(key, item === null ? 'null' : String(item))\n" +
  "      }\n" +
  "    } else {\n" +
  "      normalizedParams.append(key, value === null ? 'null' : value.toString())\n" +
  "    }"
```

Two properties make a patch like this safe to keep long-term: it is a regex over
generated output (so it survives `clean: true`), and it is idempotent (a re-run finds no
matches and changes nothing). **Add a regression test alongside it** that asserts
`getXUrl({ status: ["A", "B"] })` produces `status=A&status=B`, so an orval upgrade that
changes the underlying template makes the patch a silent no-op — and fails that test —
instead of quietly reintroducing the bug.

**Trigger to add this section's code:** the first `list[T] = Query(...)` parameter your
backend adds.

### 9.4 `clean: true` deletes hand-written files

Anything placed inside `src/generated/` is destroyed on the next generation — that is
the entire point of `clean: true`, and it is why every generated directory lives under
one parent (§2) rather than as siblings of the hand-written files. Hand-written code
lives only at `src/*.ts` (the root of `src/`, outside `src/generated/`) or in a separate
directory.

### 9.5 Peer-dependency duplication

`react`, `react-dom`, and `@tanstack/react-query` must resolve to a single copy across the
workspace. Two copies of `@tanstack/react-query` produce a silent second `QueryClient`
context and hooks that never see the provider. Pin exact React versions and use
`pnpm-workspace.yaml` `overrides` for transitive offenders:

```yaml
packages:
  - "apps/*"
  - "packages/*"

overrides:
  react-is: 19.2.4   # must track React exactly; a mismatch makes charts mount but render empty
```

### 9.6 Renaming a FastAPI handler is a frontend breaking change

`operation_id` drives hook names. Treat handler renames like public API renames (§3).

---

## 10. Rebuild checklist

**Backend**
- [ ] Every router declares explicit `tags=[...]`
- [ ] Every route declares a `response_model`, or `status_code=204` for a route with no
      body — `Dict[str, Any]` does not count as a response model
- [ ] Streaming/SSE routes carry their own tag (e.g. `tags=["streaming"]`) and are
      excluded on the frontend via `input.filters` (§3, §4.2)
- [ ] Server-to-server routes declare `include_in_schema=False`
- [ ] Every route declares a stable, convention-consistent `operation_id` — pick a
      casing and enforce it (§3)
- [ ] `app.main` imports without a DB/network connection
- [ ] `scripts/export_openapi.py` in place, `indent=2, sort_keys=True`
- [ ] `make export-openapi` target
- [ ] `server/openapi.json` committed
- [ ] A test over `app.openapi()` enforces the tag/operation-id/response-body rules
      mechanically, asserting the 2xx schema is non-empty rather than merely that a
      `content` key exists (§3)

**api-client package**
- [ ] `packages/api-client` scaffolded with the `package.json` from §4.1 — subpath
      exports point at `src/generated/{endpoints,types,zod}`
- [ ] `orval` and `prettier` pinned to exact versions (no caret); `prettier` is an
      explicit devDependency of this package
- [ ] pnpm's build-script allowlist (`allowBuilds` / `onlyBuiltDependencies`) includes
      `esbuild`, or `orval` cannot run at all
- [ ] `orval.config.ts` with both targets (§4.2): `formatter: "prettier"` (not
      `prettier: true`), `override.fetch.includeHttpResponseReturnType: false`,
      `override.mutator` pointed at a `use`-prefixed name, and **no**
      `override.query.useQuery` / `useMutation`
- [ ] `src/use-api-fetch.ts` hand-written — the hook mutator, exporting `ErrorType` so
      every generated hook's `TError` matches what it actually throws (§6.1)
- [ ] `src/index.ts` exporting only `ApiError`, `useApiFetch`, and any public types
- [ ] `scripts/postgen.mjs`, wired into `gen:api`, exits non-zero if it writes no
      barrel files
- [ ] `pnpm --filter @acme/api-client gen:api` runs clean; `tsc --noEmit` passes
- [ ] Generated output committed, entirely under `src/generated/`

**App**
- [ ] `transpilePackages` includes every workspace package
- [ ] `NEXT_PUBLIC_API_URL` in `.env.example` and `.env.local`
- [ ] `AuthProvider` sits above `QueryProvider` and anything issuing a query — no
      `ApiClientProvider`, no ordering requirement beyond that
- [ ] `QueryProvider` creates the `QueryClient` inside `useState`; `QueryCache` /
      `MutationCache` map errors to curated copy; query errors are gated on first load
      with a `meta` opt-out; `retry` is a predicate that skips 4xx; devtools kept,
      gated on environment
- [ ] `import "@/lib/zod-config"` first line of root layout
- [ ] `src/hooks/api/` wrapper layer + barrel; feature code imports wrappers only
- [ ] Public/unauthenticated routes bypass the generated hooks entirely and validate
      with plain `fetch` + generated Zod (§6.6) — the same pattern any other
      out-of-React call needs (§6.1)

**Guardrails**
- [ ] `scripts/check-contract.sh` (or equivalent) re-runs both commands from §1 and
      fails on any diff or untracked file under the two artifact paths
- [ ] `make check-contract` locally, and the same target run from CI on pull requests —
      no secrets required
- [ ] CI: the Python dependency sync includes whatever group the contract test needs
      (e.g. `uv sync --frozen --group test`); the pnpm setup pins an explicit version if
      the workspace has no `packageManager` field
- [ ] Regression test for array query-param serialization, if and when that patch is
      added (§9.3)
- [ ] Lint rule or review convention: no hand-written API request/response types outside
      `api-client`
- [ ] Documented rule: spec export + regeneration land in the same commit
