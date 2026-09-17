# Authentication System

## Overview

Authentication is handled by [Clerk](https://clerk.com). There are no register/login endpoints — users authenticate via Clerk's hosted UI and the backend validates their JWT tokens. Users are automatically provisioned in the database on first access (JIT provisioning).

The platform role (`user` | `admin`) travels on the same token as a custom `role`
claim — there are no Clerk Organizations in this template, so there is no tenant
context anywhere in this flow. See [`../../docs/setup/clerk.md`](../../docs/setup/clerk.md)
for how the claim gets onto the token.

## Architecture

```
Request
  |
  v
AuthMiddleware              Extracts JWT, verifies via JWKS (RS256)
  |                         Stores clerk_id and role in request.state
  v
get_current_user (DI)       JIT provisioning: DB -> Clerk API
  |                         Stores internal user_id in request.state.user_id
  v
Route Handler               Receives User via CurrentUser, Role via CurrentRole
```

## Dual ID System

| ID | Type | Purpose |
|----|------|---------|
| `id` | UUID string (PK) | Internal DB relationships, foreign keys |
| `clerk_id` | Text (unique, indexed) | Auth lookups, Clerk API calls |

All foreign keys (e.g., `conversation.user_id`) reference the internal `id`. The `clerk_id` is only used at the authentication boundary.

## Key Components

### 1. JWT Verification — `app/utils/auth.py`

`ClerkJWTVerifier` uses **PyJWT + JWKS** to verify Clerk-issued tokens:
- Algorithm: **RS256** (asymmetric)
- Keys fetched from `{CLERK_ISSUER}/.well-known/jwks.json`, cached by `PyJWKClient` (1-hour lifespan)
- Validates `exp` (expiration) and `iss` (issuer) claims
- Validates the token party: a session token's `azp` claim must be in `ALLOWED_ORIGINS`,
  **or** an OAuth access token's `client_id` must match `CLERK_OAUTH_CLIENT_ID` (the
  Swagger `/docs` Authorize flow). Neither present → rejected as
  `token_party_not_allowed`. See `docs/setup/clerk.md` §4–5 for the operational
  consequences, including why this makes `/docs` unsuitable for testing role-gated
  endpoints.

### 2. Auth Middleware — `app/api/middlewares/auth.py`

`AuthMiddleware` runs on every request, permissively:
- Extracts the Bearer token from `Authorization`, verifies it via `ClerkJWTVerifier`
- Stores `clerk_id` (the JWT `sub` claim) and `role` (the custom `role` claim, or
  `None`) on `request.state`
- **Never blocks a request** — route dependencies enforce auth and role

### 3. Auth Dependencies — `app/api/dependencies/authentication.py`

- **`get_clerk_id(request)`** — reads `clerk_id` from `request.state`; raises `401` if absent
- **`get_current_user(clerk_id, session)`** — resolves `clerk_id` to a `User` object via JIT provisioning; sets `request.state.user_id` to the internal UUID
- **`get_current_role(request)`** — reads the `role` claim from `request.state`, converts it to the `Role` enum; raises `403` if absent or unrecognised

Type aliases used in route signatures: `CurrentUser = Annotated[User, Depends(get_current_user)]`, `CurrentRole = Annotated[Role, Depends(get_current_role)]`.

### 4. Role Guards — `app/api/dependencies/authorization.py`

`require_role(*allowed: Role)` is a dependency factory: it depends on
`get_current_role` and raises `AuthorizationError` (403) if the resolved role is not in
`allowed`. `AdminOnly = require_role(Role.ADMIN)` is the one guard the template ships,
used by `GET /api/v1/admin/ping` (`app/api/v1/admin.py`) — the worked example of the
role seam end to end.

**There is deliberately no database mirror of the role, and no fallback to the Clerk
API for role lookup.** The token is the only source: a role change in the Clerk
dashboard takes effect on the user's next token refresh, and nothing about it can go
stale independently of the token. This is also why an OAuth access token from Swagger's
Authorize flow — which carries no `role` claim — always resolves to "no role", 403,
even for an admin: it is not a bug, it is the absence of a fallback working as intended.

### 5. JIT User Provisioning — `app/services/user/service.py`

`UserService.resolve_user(clerk_id, session)` follows this flow:

1. **DB lookup** — query by `clerk_id` (unique + indexed, so a single index scan)
2. **Clerk API** — fetch user from Clerk, create in DB

Race condition handling: if two concurrent requests try to create the same user, the `IntegrityError` on the unique `clerk_id` constraint is caught, and the existing user is fetched instead.

There is deliberately **no `clerk_id -> user_id` cache**. A hit would still cost one indexed lookup, and FastAPI caches each `Depends` result per request (`use_cache=True` by default), so a single request never resolves the user twice anyway.

### 6. Clerk Client — `app/integrations/clerk/client.py`

`ClerkClient` wraps the `clerk-backend-api` SDK:
- `get_user(clerk_id)` — fetches user data from Clerk API
- `get_primary_email(clerk_user)` — extracts primary email from Clerk user object

Called via `asyncio.to_thread()` since the SDK is synchronous.

### 7. User Repository — `app/services/user/repository.py`

`UserRepository` handles all user DB operations via SQLModel/SQLAlchemy:
- `get_by_id()`, `get_by_clerk_id()`, `get_by_email()`
- `create_or_get()` — creates a user from Clerk data, or returns the existing row on a race
- `update_from_clerk()` — syncs profile changes
- `delete()`

## Swagger UI OAuth2

The `/docs` page has an "Authorize" button that triggers Clerk's OAuth2 Authorization Code flow. Configured in `app/main.py` via `swagger_ui_init_oauth`. Requires:
- `CLERK_OAUTH_CLIENT_ID` — a public client (PKCE, no secret). `make clerk-bootstrap-oauth`
  registers one and writes all three env vars; by hand it is Dashboard → OAuth applications.
- Redirect URI `http://localhost:8100/oauth2-redirect`, registered on that client. It must
  match `swagger_ui_oauth2_redirect_url` verbatim — Clerk rejects the whole authorize
  request otherwise.

It authenticates fine — but see §1 and §4 above: the resulting token carries no `role`
claim, so it cannot exercise a role-gated route.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CLERK_SECRET_KEY` | Clerk Backend API secret key |
| `CLERK_ISSUER` | Clerk instance URL (e.g., `https://your-instance.clerk.accounts.dev`) |
| `CLERK_OAUTH_CLIENT_ID` | OAuth app client ID (for Swagger UI) |
| `CLERK_AUTHORIZE_URL` | OAuth authorize endpoint |
| `CLERK_TOKEN_URL` | OAuth token endpoint |
