# Server — FastAPI Backend

Continuation of the root `CLAUDE.md`. Covers `server/` conventions only — no repeated project or stack overview.

---

## Running the Server

All commands below run from `server/`. For the full Docker stack, use root `make` commands (see root `CLAUDE.md`).

```bash
make install          # pip install uv + uv sync
make dev              # dev server on :8100 (hot reload, APP_ENV=development)
make staging          # uvicorn in staging env
make prod             # uvicorn in production env
```

Env file is selected by `APP_ENV`. Copy `server/.env.example` → `.env.development` before first run.

### Server-only Docker

```bash
make docker-run                            # dev stack: server + db (APP_ENV=development)
make docker-run-db ENV=development         # database only
make docker-logs ENV=development           # follow server + db logs
make docker-stop ENV=development           # stop the stack, database included
make docker-logs-server ENV=development    # follow the server container only
make docker-stop-server ENV=development    # stop the server, leave the database up
```

These all drive `../docker-compose.dev.yml`, which bind-mounts `./server/app`
over the image's code. That is why `docker-run` takes no `ENV`: a
`ENV=production` variant would run production secrets against your working
tree. Production runs from `docker-compose.prod.yml`, via the root `Makefile`.

`docker-logs-server` and `docker-stop-server` delegate to
`scripts/logs-docker.sh` and `scripts/stop-docker.sh`, which address the
Compose *service* rather than a container name — `docker-compose.dev.yml` pins
`container_name: server` while the prod file does not, so the name is Compose's
to resolve.

### Database Migrations (Alembic)

These run on the **host** via `uv`, against the DB named in `server/.env.<ENV>`.
Use them to author revisions:

```bash
make migrate ENV=development                          # apply all pending migrations
make migrate-create ENV=development MSG='add orders'  # generate new migration
make migrate-downgrade ENV=development                # rollback one step (REV=-1 default)
make migrate-history ENV=development                  # show migration history
make migrate-current ENV=development                  # show current revision
```

In Docker, migrations are a **discrete release phase**, not part of app startup.
A one-shot `migrate` service runs `alembic upgrade head`, and `server` is gated
on it via `depends_on: condition: service_completed_successfully`. A failed
migration therefore fails the `up` and leaves any previously running container
serving the old image, instead of crash-looping the app.

The service runs `scripts/migrate.sh`. **Add further release-phase steps there**
(seeding, backfills, first-admin bootstrap) rather than in the compose
`command:` — one script, two compose files pointing at it. Anything added must
be idempotent: it runs on every `up`, including a restart with nothing to do.

From the repo root: `make docker-migrate` applies them on demand,
`make docker-migrate-status` prints the current revision. Never reintroduce
`alembic upgrade` into `scripts/docker-entrypoint.sh` — that entrypoint is
env-prep only, for both services.

Two caveats:
- `depends_on` applies to `compose up`, not to reboots. After a Docker daemon or
  host restart, `server` comes back under its restart policy with no `migrate`
  run. Benign (the DB is already migrated), but it is not a startup guarantee.
- `app/`, `alembic/`, and `scripts/` are bind-mounted in dev, so the container
  always executes the working tree. `alembic.ini` is **not** — changes to it
  need `make docker-build-api`.

### Linting

```bash
make lint     # ruff check
make format   # ruff format
```

---

## Directory Structure

```
server/
├── app/
│   ├── api/
│   │   ├── v1/              # Route handlers: admin.py, auth.py, chatbot.py, conversation.py, webhooks.py
│   │   ├── dependencies/    # FastAPI deps: db session, current user, conversation ownership
│   │   ├── middlewares/     # Auth (JWT), access logging, correlation ID, rate limiting
│   │   └── system/          # Health + Prometheus metrics endpoints
│   ├── agents/
│   │   ├── base/            # Abstract BaseAgent class
│   │   ├── shared/          # memory/, checkpointing/, observability/
│   │   └── chatbot/         # graph.py, state.py, prompts/, tools/
│   ├── core/                # Settings (config.py), app factory
│   ├── database/            # Async engine, session factory
│   ├── exceptions/          # base.py — exception hierarchy
│   ├── integrations/        # Third-party protocols: clerk/ (client + webhooks/)
│   ├── models/              # SQLModel ORM models (user.py, conversation.py)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic: user/, conversation/, llm/
│   └── utils/               # Shared utilities
└── tests/
    ├── unit/                # No external deps — middleware, models, schemas, services, utils
    └── integration/         # Requires DB — dependencies, API routes, services
```

`services/` and `integrations/` are deliberately distinct. `services/` holds domain
logic. `integrations/` holds code that exists only because a third party does — one
package per provider, carrying **both** directions of traffic: the outbound client we
call, and the inbound webhook machinery they call. A provider's verification, event
schemas, dispatch and handlers all live together so the flow reads top to bottom.

---

## Code Conventions

- `async def` everywhere — no blocking I/O
- Type hints on all function signatures
- Pydantic models over raw dicts (RORO pattern)
- File names: `lowercase_with_underscores.py`
- All imports at the top of the file — never inside functions

---

## Logging (structlog)

```python
# ✅ Correct
logger.info("conversation_created", conversation_id=conversation_id, user_id=user_id)
logger.exception("db_query_failed", table="conversations")

# ❌ Wrong
logger.info(f"Document {doc_id} uploaded")  # no f-strings in events
logger.error("something failed")  # use .exception() to preserve tracebacks
```

- Event names: `lowercase_with_underscores`
- Variables as kwargs, never interpolated into the event string
- HTTP access logs → `AccessLogMiddleware` (never log manually in routes)
- Bind component context: `logger.bind(component="service")`
- All requests get a `correlation_id` via `asgi-correlation-id` — auto-bound to logs and included in error responses

---

## Exception Handling

Services raise domain exceptions; the centralized handler translates them to HTTP. **Never** raise `HTTPException` from services. **Never** add try/except in route handlers.

```python
# In a service
from app.services.conversation.exceptions import ConversationNotFoundError

raise ConversationNotFoundError("Conversation not found", conversation_id=conversation_id)


# In a route — no try/except needed
@router.delete("/conversation/{conversation_id}")
async def delete_conversation(conversation: UserConversation):
    return await conversation_service.soft_delete_conversation(db_session, conversation.id)
```

Base exceptions live in `app/exceptions/base.py`:

| Class | HTTP |
|---|---|
| `NotFoundError` | 404 |
| `AuthenticationError` | 401 |
| `AuthorizationError` | 403 |
| `ConflictError` | 409 |
| `ValidationError` | 422 |
| `DatabaseError` | 500/503 |

Each service package defines its own exceptions extending these. New service exceptions go in `app/services/<name>/exceptions.py`; integration exceptions go in `app/integrations/<provider>/exceptions.py`.

---

## API Contract

`server/openapi.json` is a committed artifact. It generates the frontend's
TanStack Query hooks, TypeScript types and Zod validators, so the schema is a
published interface, not a by-product.

The schema's `info` block and its `/api/v1` prefix come from
`[tool.app.metadata]` and `[project]` in `pyproject.toml`, loaded by
`app/core/metadata.py`. Never move them into `Settings`: an env-derived title or
prefix makes the exported artifact machine-dependent, which
`tests/unit/scripts/test_export_openapi.py` asserts against.

Every route must therefore declare:

- **An explicit tag.** Tags become directory names and module boundaries in the
  generated client. Untagged routes collapse into a `default` bucket.
- **An explicit camelCase `operation_id`** — `getMe`, `listConversations`.
  FastAPI's auto-generated ids (`health_check_health_get`) become hook names
  like `useHealthCheckHealthGet`.
- **Either a `response_model` or `status_code=204`.** A route with neither
  generates `unknown` on the client. `Dict[str, Any]` is not a response model:
  it emits `additionalProperties: true` and generates
  `{[key: string]: unknown}`.

Two further rules:

- **Server-to-server routes declare `include_in_schema=False`.** The Clerk
  webhook receiver already does; the frontend must never get a hook for it.
- **Streaming routes declare `tags=["streaming"]`** and are exempt from the
  response-body rule. They have no JSON body, and orval excludes the tag. They
  remain visible in Swagger.

**`operation_id` is a public frontend symbol.** Renaming a handler renames a
hook. Treat it as a breaking change.

**Regenerate in the same commit.** After changing any route, run
`make gen-contract` from the repo root — it re-exports the spec and regenerates
the client — and commit both outputs alongside the route change.
`make check-contract` does the same and then fails on drift; that is what CI
runs, and what `make docker-build*` gates on. With `core.hooksPath` configured
(root `CLAUDE.md`), the pre-commit hook regenerates and blocks any commit that
touches `app/` without them.

`tests/unit/api/test_openapi_contract.py` enforces the three per-route rules
mechanically. It needs no database.

---

## Authentication

- Clerk JWTs verified by `AuthMiddleware` (RS256); `clerk_id` set on `request.state`
- Use `CurrentUser` dependency for protected endpoints:
  ```python
  async def endpoint(user: Annotated[User, Depends(get_current_user)]):
  ```
- Users are JIT-provisioned in the local DB on first request via `UserService`
- Conversation ownership enforced by the `UserConversation` dependency

**Role gating** is separate from identity. `CurrentRole` reads the `role` claim off
the token without provisioning a user; `require_role(*allowed)` in
`app/api/dependencies/authorization.py` builds a dependency that 403s callers
outside the allowed roles, and `AdminOnly` is `require_role(Role.ADMIN)`. A route
gated on `AdminOnly` alone never touches the DB or sets `request.state.user_id` —
add `CurrentUser` too if the route needs the provisioned user (see
`app/api/v1/admin.py`).

---

## Settings Access

Pydantic nested models in `app/core/config.py`. Domains: `database`, `llm`, `langfuse`, `memory`, `auth`, `logging`, `rate_limits`, `cors`, `evaluation`.

```python
# ✅ Correct — unpack SecretStr
api_key = settings.llm.OPENAI_API_KEY.get_secret_value()

# ❌ Wrong — returns SecretStr object, not the string
api_key = settings.llm.OPENAI_API_KEY
```

---

## Agent Architecture

All agents extend `BaseAgent` (`app/agents/base/`) and must implement `create_graph()`.

**Shared components:**
- `app/agents/shared/memory/` — `get_relevant_memory()`, `update_memory()`, `delete_user_memory()`
- `app/agents/shared/checkpointing/` — `AsyncPostgresSaver` for LangGraph persistence, plus `delete_conversation_checkpoints()`
- `app/agents/shared/observability/` — `create_graph_config()` wires Langfuse callbacks

`BaseAgent` provides `get_response()`, `get_stream_response()` and `get_chat_history()` with memory and tracing built in. Clearing a conversation is **not** an agent method: checkpoints are keyed by `thread_id` in tables every agent shares, so use `delete_conversation_checkpoints()` from `app/agents/shared/checkpointing/` and do not take an agent parameter just to reach it. All LLM calls must have Langfuse tracing. All retries must use `tenacity` with exponential backoff.

---

## Testing

Tests live in `server/tests/` split into two layers:

```
tests/
├── unit/          # Pure logic, no external deps — mock everything external
│   ├── api/       # Dependency logic (auth, etc.)
│   ├── config/    # Settings loading
│   ├── exceptions/
│   ├── integrations/  # Provider clients, webhook verification and handlers
│   ├── middleware/
│   ├── models/
│   ├── schemas/
│   ├── services/  # Service logic with mocked DB/Clerk/LLM
│   └── utils/
└── integration/   # Requires a live DB connection
    ├── api/       # Full route tests via TestClient
    ├── dependencies/
    └── services/
```

Run from `server/`:

```bash
make test              # all tests (APP_ENV=test)
make test-unit         # unit tests only
make test-integration  # integration tests only
make test-coverage     # all tests + HTML/XML coverage report
make test-fast         # all tests, skipping slow ones

# Target a specific file or test name
APP_ENV=test uv run pytest tests/unit/services/test_user_erasure.py
APP_ENV=test uv run pytest -k "test_name"
```

Coverage is reported automatically (`--cov=app`). HTML report written to `htmlcov/`.

New tests mirror the `app/` structure: a test for `app/services/llm/service.py` goes in `tests/unit/services/test_llm_service.py`. Unit tests mock external deps (DB, Clerk, LLM); integration tests use a real DB.

---

## GDPR — Right to Erasure

When a user is deleted (`DELETE /api/v1/auth/me`), in order:

1. Clerk deletion (JWTs immediately invalidated)
2. LangGraph checkpoints hard-deleted (`delete_conversation_checkpoints`)
3. mem0 memories deleted (`delete_user_memory`)
4. User PII anonymized via `AnonymizableMixin.anonymize_user()`
5. Conversation records soft-deleted

Rules:
- Never use `SoftDeleteMixin` on `User` — it leaves PII in the DB
- New models with PII must implement `AnonymizableMixin` and an `anonymize_*()` method
- Always call `delete_conversation_checkpoints()` before soft-deleting a conversation
