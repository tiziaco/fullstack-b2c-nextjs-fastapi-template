# Web App

The template's application — the app users sign in to. It ships with no example
domain; `/home` is the one placeholder page to replace.

Runs on **http://localhost:3000**.

---

## Overview

This is a [Next.js 16](https://nextjs.org/) application using the App Router, part of the `web-app` pnpm monorepo.

**Key pages:**

| Route | Description |
|---|---|
| `/home` | Main dashboard |
| `/sign-in` | Clerk-powered sign-in |
| `/sign-up` | Clerk-powered sign-up |

---

## Getting Started

### 1. Set up environment variables

```bash
cp .env.example .env.local
```

Edit `.env.local` and fill in your Clerk API keys and other required values:

```env
NEXT_PUBLIC_API_URL=http://localhost:8100

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...

NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/home
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/home
```

The `NEXT_PUBLIC_CLERK_*` values are read by the Clerk SDK straight from the
environment, not by any code in this repo — so grepping for them finds only config and
docs.

The `NEXT_PUBLIC_*` values are **inlined at image build time**, not read at runtime, so
changing one means rebuilding the image.

Getting the keys is only half of it — Clerk also needs `publicMetadata.role` set on
users, the session token customized to carry it as a `role` claim, and this app's origin
listed in the server's `ALLOWED_ORIGINS`. See [`docs/setup/clerk.md`](../../../docs/setup/clerk.md).

### 2. Install dependencies

From the `web-app/` directory:

```bash
pnpm install
```

### 3. Run the dev server

```bash
# from web-app/
pnpm dev:web

# or from this directory
pnpm dev
```

The app will be available at http://localhost:3000.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16, React 19, App Router |
| Language | TypeScript 5 (strict) |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui + Base UI (`@base-ui/react`) + Lucide React |
| Auth | Clerk (`@clerk/nextjs` v6) |
| Data Fetching | TanStack Query v5 |
| Validation | Zod v4 |
| Notifications | Sonner |

---

## Project Structure

```
src/
├── app/
│   ├── (dashboard)/   # Authenticated routes (home)
│   ├── (auth)/        # Auth routes (sign-in, sign-up)
│   ├── layout.tsx     # Root layout
│   └── page.tsx       # Root redirect
├── components/
│   ├── layout/        # Sidebar, header, shell components
│   └── settings/      # Settings UI
├── hooks/             # Custom React hooks
├── lib/               # Utilities, API helpers, env config
├── providers/         # React context providers
├── proxy.ts           # Clerk middleware
└── styles/            # Global CSS
```

### Branding

Two files carry the visual identity — swap them for your own:

| File | Used by |
|---|---|
| `public/images/logo-small.png` | the sidebar mark, via `logoSrc` on `AppSidebar` (`@app/ui`, `packages/ui/src/components/layout/company-logo.tsx`) |
| `public/icons/favicon.ico` | the browser tab, via `metadata.icons` in `src/app/layout.tsx` |

The accompanying `logoAlt` and `metadata.title` strings live in
`src/app/(dashboard)/layout.tsx` and `src/app/layout.tsx`.

---

## Auth & Roles

Authentication is handled by Clerk. The platform role (`user` | `admin`) is a plain
`publicMetadata.role` value, carried on the session token as a custom `role` claim —
there is no organization behind it. `@app/auth` reads it:

```typescript
import { useAppAuth, Role } from '@app/auth'

const { user, role, isLoaded } = useAppAuth()
if (role === Role.ADMIN) { ... }
```

`<Protect role="...">` is not used here — that prop gates Clerk *organization* roles,
which this template does not have. Gate explicitly on `role` from `useAppAuth()`
instead. See `web-app/CLAUDE.md` for the full rationale and the server-side equivalent.

---

## Shared Packages

- **`@app/ui`** — shared shadcn/ui components
- **`@app/auth`** — `Role` enum, `useAppAuth()`, `getUserRole()`
- **`@app/api-client`** — generated API client (types, endpoints, hooks) from the OpenAPI spec

Always check `packages/ui` before creating new components.
