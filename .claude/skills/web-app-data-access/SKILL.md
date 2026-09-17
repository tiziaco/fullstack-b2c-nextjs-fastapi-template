---
name: web-app-data-access
description: >
  How a component in this Next.js workspace gets data from the FastAPI server. Use whenever wiring a
  page or component to the API, adding a new endpoint call, choosing between a Server Component and a
  client hook, fetching in a route handler, middleware or script, calling a streaming route, or handling
  an API error. Trigger on tasks like "fetch X on this page", "call the /api/v1/... endpoint", "load this
  server-side", "add a mutation", "make this a Server Component", "poll for status", "stream the
  response", or any work touching apps/web/src/app/, packages/api-client/, or a component that renders
  server data. Use this instead of generic Next.js data-fetching advice — the generic default is wrong
  here, and this file says why.
---

# Web App Data Access

Generic Next.js guidance says "Server Components first, add client fetching only when you need
interactivity." **That default is inverted in this workspace**, and not by preference.

`useApiFetch` (`packages/api-client/src/use-api-fetch.ts`) — the mutator every orval-generated
endpoint routes through — is a React hook, deliberately. Its docstring records the reason: a
module-scope client would be shared across concurrent requests in a Next.js server process, so one
user's token could serve another user's request, and it would freeze the first render's `getToken`
closure.

The consequence: **every generated hook is client-only.** A Server Component that wants data must
leave the generated client behind and hand-write a fetch — which also means hand-forwarding the Clerk
token and losing the central error→toast mapping in `QueryProvider`.

So the question is never "Server or Client?" in the abstract. It is: **is this data worth giving up
the generated client for?**

## Decision

Start at the top. Take the first row that matches.

| The data is… | Use | Cost |
|---|---|---|
| Anything reachable by a generated hook, rendered in the browser | **Generated hook** — `useGetX()` from `@app/api-client/endpoints/<tag>` | `"use client"` on that component |
| A mutation (create/update/delete) | **Generated mutation hook** | same |
| Polling, filters, search, infinite scroll, optimistic updates | **Generated hook** + TanStack Query options | same |
| From a route carrying the `streaming` tag | **Plain `fetch`** — streaming routes are excluded from generation, so no hook exists | manual auth + errors |
| Needed before first paint, above the fold, and measurably hurt by a client round-trip | **Hand-written server fetch** — see `references/server-side-fetch.md` | you own auth, types and errors |
| Needed in a route handler, `proxy.ts`, or a node script | **Hand-written server fetch** — no React context exists there | same |

**The default is the first row.** Reach past it only with a reason you could write down. "Server
Components are the modern default" is not one — in this repo it is a downgrade.

### Why the client path is not a compromise here

The generated hook gives you four things the server path makes you rebuild:

1. **Auth.** `useApiFetch` reads the live Clerk token on every call via `useAppAuth()`.
2. **Types.** Request and response types come from the committed OpenAPI contract. A hand-written
   type describing an API payload is a bug.
3. **Errors.** Every hook's `error` is an `ApiError` — `{ status, body, requestId }`.
4. **Error copy.** `QueryProvider` maps `error.status` to curated copy in
   `@app/core/constants/messages` and toasts it centrally. Server-authored text never reaches the UI.

Point 4 is a security boundary, not a convenience. See `query-provider.tsx`'s `toastForError`.

## Using a generated hook

```tsx
"use client"

import { useGetReadiness } from "@app/api-client/endpoints/system"
import { Skeleton } from "@app/ui"

export function ServerStatus() {
  const { data, isPending } = useGetReadiness()

  if (isPending) return <Skeleton className="h-4 w-24" />
  return <span>{data.status}</span>
}
```

Rules:

- Import **per tag** (`/endpoints/system`), never from a barrel. The tag is the route's FastAPI tag.
- Do not write a `try/catch` to toast. `QueryProvider` already did. Only handle `error` locally when
  this component needs a *different* outcome than the toast — inline empty state, a retry affordance.
- Never render `error.message` or `error.body`. Map `error.status` to `@app/core/constants/messages`.
- Never return `null` while loading. Return a skeleton.
- A background refetch that fails does **not** toast if the query already has data — that is
  intentional (`query-provider.tsx`). A polling query that should never toast sets
  `meta: { silentError: true }`.

## Error handling, wherever the data came from

One rule holds on both paths: **the server's words never reach the user.** Status codes map to copy
you wrote.

```tsx
// ✅ a status maps to copy we control
if (error.status === 404) toast.error(messages.toasts.notFound)

// ❌ server-authored text — may carry stack traces or internal route names
toast.error(error.message)
toast.error(String(error.body))
```

## Never

- **Never create `apps/web/src/lib/api/`.** The generated client is that layer. If you are reaching
  for it, you are either on the server path (use `references/server-side-fetch.md`, which puts the
  helper next to its route) or you are about to hand-write something orval already generated.
- **Never hand-edit `packages/api-client/src/generated/`.** orval runs with `clean: true`.
- **Never change a server route without `make gen-contract` in the same commit.** The pre-commit hook
  blocks it; the image build and CI fail on it.
- **Never call a generated hook outside a Client Component.** It calls `useAppAuth()` and will throw.

## Reference

| File | Read when |
|---|---|
| `references/server-side-fetch.md` | You took a server row in the decision table, or need a route handler / middleware / script to call the API |
