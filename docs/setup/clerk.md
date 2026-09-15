# Clerk — Setup Procedure

Everything you must do **in the Clerk dashboard** before this stack authenticates
anyone, plus the environment variables each step produces.

Do this first. Then [`clerk-webhooks.md`](./clerk-webhooks.md) for event delivery.
For how the code consumes the token once it arrives, see
[`../../server/docs/authentication.md`](../../server/docs/authentication.md).

**Most of this is scripted.** With the [Clerk CLI](https://clerk.com/docs/cli) installed
and `clerk auth login` done once:

```bash
make clerk-bootstrap-env    # create the app, write keys to all three env files
make clerk-apply-config     # §1's role claim, §2's sign-in settings
make clerk-seed-users       # two dev users, pre-verified, ready to sign in
```

Three things those commands do **not** do, each explained where it comes up below:
`ALLOWED_ORIGINS` (§4), the Swagger OAuth app (§5), and the webhook signing secret (§6).
The dashboard walkthrough in each section remains correct — read it when you want to know
what the scripts are doing, or when you are configuring an instance by hand.

Clerk is the only identity provider wired in. There is no local password store and no
login endpoint to build. **This template does not use Clerk Organizations** — the
platform role is a plain user attribute, not a tenant membership.

---

## What you are creating

| In Clerk | Produces | Consumed by |
|---|---|---|
| An application | publishable + secret key | the web app, the server |
| `publicMetadata.role` on each user | the value the session token customization reads | `Role` enum, `require_role()`, `useAppAuth()` |
| A session token customization | a `role` claim on every session token | `get_current_role()` on the server; `AuthProvider` on the client |
| (optional) An OAuth app | `CLERK_OAUTH_CLIENT_ID` | the Authorize button on `/docs` |
| A webhook endpoint | `CLERK_WEBHOOK_SIGNING_SECRET` | see `clerk-webhooks.md` |

---

## 1. Set the platform role on your users

```bash
make clerk-seed-users
```

Creates the users in [`scripts/clerk/dev-users.json`](../../scripts/clerk/dev-users.json) —
two of them, one per role — with the role already on `publicMetadata`. Users created through
the Backend API have their email addresses verified on creation and carry the password from
that file, so there is no verification code to collect and nothing to click. Re-running is a
no-op; a role changed in the roster is merged on the next run.

That file is committed on purpose. The emails are fake, the passwords are throwaway, and the
script refuses to run against anything but a development instance.

**By hand:** Dashboard → Users → select a user → Metadata → Public. Add:

```json
{ "role": "user" }
```

or `"admin"` for a platform administrator. These are the only two values
`server/app/models/enums.py` and `web-app/packages/auth/src/permissions.ts` recognise.

> Seeded users still get 401s until `ALLOWED_ORIGINS` (§4) lists the web app's origin.
> Nothing in the scripted path sets it.

---

## 2. Customize the session token to carry the role claim

```bash
make clerk-apply-config
```

Applies [`scripts/clerk/config.json`](../../scripts/clerk/config.json), the committed copy
of the instance's settings. It holds the claim below, and alongside it the settings that let
a seeded user actually sign in: password authentication on, the second-factor device-trust
challenge off, and — the one that catches people — the Have I Been Pwned check off **at
sign-in**. Creating a user with a weak password bypasses HIBP, but signing in as them does
not, so without that line a seeded account exists and cannot log in.

`make clerk-check-config` re-pulls the instance and fails if someone has changed it in the
dashboard, so the file stays truthful. One blind spot, by design: the API never returns the
session block, so drift in this claim specifically cannot be detected — re-apply if you
suspect it.

**By hand:** Dashboard → Sessions → Customize session token. Add:

```json
{ "role": "{{user.public_metadata.role}}" }
```

This is what turns `publicMetadata.role` — an attribute on the user, invisible to the
token by default — into a `role` claim on every session token the frontend and the
backend both see. Skip this step and every request gets a token with no `role` claim:
`get_current_role()` (`server/app/api/dependencies/authentication.py`) raises
`AuthorizationError("No role in token")`, and `useAppAuth()`'s `role` is always `null`.

**The role has no database mirror and no caching.** `get_current_role()` reads the
`role` claim straight off the verified token, every request — there is deliberately no
DB column and no fallback to the Clerk API for role lookup. A role change in the
dashboard takes effect on the user's **next token refresh**, and nothing about it can go
stale independently of the token itself.

A signed-in user with no role claim at all — the customization above not configured, or
`publicMetadata.role` unset — is authenticated but has no platform role: every
role-gated route or component treats them as unauthorized. That looks like a permissions
bug, not a missing-configuration problem — see the symptom table at the end.

---

## 3. Keys

```bash
make clerk-bootstrap-env
```

Creates the application (named by `CLERK_APP_NAME`, default `B2C Template Dev`) and writes
every value in the two tables below except the OAuth trio and the webhook secret. It fills in
all three env files, creating any that are missing from their `.env.example`, and leaves
unrelated keys alone.

`CLERK_ISSUER` is not something the CLI hands you — it is derived. A publishable key is
base64 of the frontend-API host, so the issuer falls out of the key itself.

The script also writes `CLERK_APP_ID` to the root `.env`; every other `clerk-*` target reads
it from there.

> **Rebuild the web image afterwards.** `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is inlined into
> the image at build time, so a web container built before this step keeps serving the old
> key and Clerk silently talks to the wrong instance:
>
> ```bash
> make docker-build-web && make docker-run-core
> ```
>
> The symptom is a sign-in page that renders but authenticates against nothing you
> configured. Confirm which key is actually live with:
>
> ```bash
> curl -s http://localhost:3000/sign-in | grep -o 'pk_test_[A-Za-z0-9]*' | head -1
> ```

**By hand:** Dashboard → API keys.

Server — `server/.env.<environment>`:

| Variable | Value |
|---|---|
| `CLERK_SECRET_KEY` | `sk_test_…` / `sk_live_…` |
| `CLERK_ISSUER` | your instance URL, e.g. `https://your-app.clerk.accounts.dev` |

`CLERK_ISSUER` is the trust anchor, not a display setting: the JWKS URL used to verify
every RS256 signature is derived from it (`AuthSettings.jwks_url`).

The web app — `web-app/apps/web/.env.local`:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_test_…` / `pk_live_…` |
| `CLERK_SECRET_KEY` | same secret key |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/sign-up` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL` | `/home` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL` | `/home` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8100` in dev |

None of these are read by application code. The Clerk SDK picks them up from the
environment itself — `mergeNextClerkPropsWithEnv` in `@clerk/nextjs` maps each one onto
a `<ClerkProvider>` prop — which is why grepping the repo for them finds only config
files and docs.

> **The `NEXT_PUBLIC_*` values are baked in at image build time**, not read at runtime —
> Next.js inlines them. Changing one means rebuilding.

---

## 4. `ALLOWED_ORIGINS` — the setting that fails like a bug

In `server/.env.<environment>`. It gates **two** things, which is why a missing entry is
so confusing:

1. **CORS** (`app/api/middlewares/cors.py`) — the browser calls the API cross-origin;
   there is no server-side proxy hop.
2. **The Clerk `azp` token-party check** (`app/utils/auth.py`). A session token carries
   `azp` = the origin that requested it. If that origin is not listed, the token is
   rejected as `token_party_not_allowed` — **a valid, unexpired, correctly-signed token
   is refused.**

So the web app's origin must be listed, per environment:

```bash
# JSON array — see the warning below
ALLOWED_ORIGINS=["http://localhost:3000"]
```

> **It must be a JSON array.** `ALLOWED_ORIGINS` is a `List[str]`, and pydantic-settings
> parses complex types as JSON. A comma-separated value does not degrade — the server
> refuses to start with
> `SettingsError: error parsing value for field "ALLOWED_ORIGINS"`.

In staging and production list the real hostname the web app is deployed at. Miss it and
users get 401s from an API that is working perfectly.

---

## 5. Swagger's Authorize button (optional)

Only needed if you want to call authenticated endpoints from `/docs`.

**Dashboard → OAuth applications → create a public client** (PKCE, no secret), and
register the redirect URI `http://localhost:8100/oauth2-redirect`.

```bash
CLERK_OAUTH_CLIENT_ID=...
CLERK_AUTHORIZE_URL=...
CLERK_TOKEN_URL=...
```

OAuth access tokens carry no `azp` at all — they are authorised by `client_id` matching
`CLERK_OAUTH_CLIENT_ID` instead, which is why `/docs` works without its own origin in
`ALLOWED_ORIGINS`.

> **This makes `/docs` a bad way to test the admin role.** OAuth access tokens carry
> `client_id`, not the session-token-template claims — so they never carry the custom
> `role` claim configured in §2 either. `GET /api/v1/admin/ping`
> (`server/app/api/v1/admin.py`) will 403 from Swagger even when the signed-in user's
> `publicMetadata.role` is `admin`. **This is correct behaviour, not a bug**: the server
> deliberately has no fallback to the Clerk API for role lookup (see §2), so an OAuth
> token with no role claim is indistinguishable from a token with no role at all. Test
> role-gated endpoints from the web app itself, where `useAppAuth()`'s token carries the
> claim.

---

## 6. Webhooks

User events (JIT provisioning, offboarding) arrive by webhook. Full procedure, including
the ngrok tunnel for local delivery: [`clerk-webhooks.md`](./clerk-webhooks.md).

**This step cannot be scripted.** `CLERK_WEBHOOK_SIGNING_SECRET` is generated with the
endpoint, and no API creates one: the Backend API offers only `POST /webhooks/svix` (create
the Svix app) and `POST /webhooks/svix_url` (mint a dashboard URL), neither of which
registers an endpoint at a URL or returns its `whsec_`. Creating the endpoint and copying
its secret stays a dashboard visit.

---

## Symptom → cause

| What you see | Likely cause |
|---|---|
| Signed in, but every role-gated route or action is refused | No `role` claim on the token — the session token customization (§2) is not configured, or `publicMetadata.role` (§1) is unset. |
| 401 from the API, token looks valid | The web app's origin is missing from `ALLOWED_ORIGINS` (§4). Server log: `token_party_not_allowed`. |
| Server won't start, `SettingsError` on `ALLOWED_ORIGINS` | Not a JSON array (§4). |
| `GET /api/v1/admin/ping` 403s from Swagger for an admin user | Expected — OAuth access tokens carry no `role` claim (§5). Test from the web app instead. |
| Browser CORS error on every request | Same as the 401 row — one setting, two symptoms (§4). |
| Roles work locally, not in staging/production | `ALLOWED_ORIGINS` is per-environment; each `server/.env.<env>` needs its own origins. |
| Role change in Clerk not taking effect | It should take effect on the user's next token refresh — there is no cache to invalidate (§2). If it still doesn't, check the token actually being sent is fresh, not one issued before the dashboard change. |
