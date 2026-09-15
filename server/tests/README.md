# Testing Guide

This directory contains the test suite for the FastAPI server application. The tests are organized into unit and integration tests, following pytest best practices.

## Setup

Tests will not run on a fresh clone without a `server/.env.test` — it is gitignored
(never committed) and must be created before `make test` works:

```bash
cp .env.example .env.test
```

Then edit two values:

- Set `APP_ENV=test` (pydantic-settings auto-loads `.env.test` when `APP_ENV=test` is
  in the process environment — `make test` and friends already export it, see below).
- Set `CLERK_WEBHOOK_SIGNING_SECRET` to exactly
  `whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw` — the `TEST_SECRET` hardcoded in
  `tests/integration/api/test_webhooks.py:18`. svix base64-decodes the signing secret in
  its `Webhook` constructor, so any other syntactically valid `whsec_...` string will
  fail signature verification and every webhook test will fail before it asserts
  anything. This is not documented anywhere else and has cost two implementers time —
  if `test_webhooks.py` fails wholesale with a verification error, this is why.

```bash
uv sync --group test
```

Integration tests additionally need a running Docker daemon: the test database runs in
a throwaway container started by [testcontainers](https://testcontainers.com/)
(`postgres_container` in `tests/conftest.py`) — no `createdb`, no database settings in
`.env.test`, and no port to configure. It gets an ephemeral host port, so it never
collides with the dev database on 5434, and it is torn down at the end of the session.
The fixture is lazy — only integration tests reach it (via `test_engine` →
`db_session`) — so `make test-unit` starts no container.

## Directory Structure

```
tests/
├── conftest.py                              # Shared fixtures (DB, clients, auth helpers)
├── unit/                                    # No DB, no network, no app startup
│   ├── conftest.py                          # Unit fixtures
│   ├── agents/                              # LangGraph tool execution, mem0 factory contract
│   ├── api/                                 # Role-based auth dependencies, OpenAPI contract rules
│   ├── config/test_settings.py              # Environment resolution, AuthSettings
│   ├── core/test_logging_third_party.py     # Rust-extension logging bridged into structlog
│   ├── exceptions/                          # Exception hierarchy, metrics counter
│   ├── integrations/clerk/                  # Clerk client, timestamps, webhook signature verification, user.* handlers
│   ├── middleware/                          # Auth middleware pass-through, Prometheus instrumentation
│   ├── models/                              # Enums, mixins, User.anonymize_user()
│   ├── schemas/                             # Pydantic validation — general + system
│   ├── scripts/test_export_openapi.py       # openapi.json export is deterministic
│   ├── services/                            # LLM registry/fallback, GDPR erasure cascade, Clerk timestamp sync
│   └── utils/                               # JWT verification (RS256, real keys), sanitization, graph helpers
└── integration/                             # Requires a live DB (testcontainers)
    ├── conftest.py                          # Auth override, mock agent, test_user fixture
    ├── api/                                 # Full route tests via TestClient — auth, admin, chatbot, conversations, health, webhooks
    ├── dependencies/                        # DB session errors/RLS, conversation ownership, role-based access control
    ├── exceptions/test_handlers.py          # Exception → HTTP mapping, no info leakage
    └── services/                            # UserRepository, ConversationService, UserService JIT provisioning
```

## Running Tests

```bash
# All tests
make test

# Unit only (fast, no DB)
make test-unit

# Integration only
make test-integration

# With coverage report
make test-coverage
```

`make test` and its siblings export `APP_ENV=test` themselves. Direct pytest (from `server/`) must set it explicitly:

```bash
# Run a specific file
APP_ENV=test uv run pytest tests/unit/utils/test_sanitization.py -v

# Run a specific test
APP_ENV=test uv run pytest tests/integration/api/test_auth.py::TestGetMe::test_authenticated_returns_200 -v

# Run by marker
APP_ENV=test uv run pytest -m unit
APP_ENV=test uv run pytest -m integration

# Stop on first failure
APP_ENV=test uv run pytest -x

# Re-run last failures
APP_ENV=test uv run pytest --lf
```

## Key Design Decisions

**Unit tests** — no DB, no network. External calls mocked via `unittest.mock.patch`. Every file has `pytestmark = pytest.mark.unit`.

**Integration tests** — real test DB (savepoint rollback — all writes auto-undone after each test). External services mocked:
- **Auth**: `get_current_user` overridden via `app.dependency_overrides` → returns `test_user` directly, bypassing JWT + JIT provisioning
- **Agent**: `get_chatbot_agent` overridden with `AsyncMock` → no OpenAI calls
- **Clerk**: patched at `app.services.user.service.clerk_client` where needed

## Fixtures

### Shared (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | function | AsyncSession with savepoint rollback |
| `client` | function | AsyncClient with `get_db_session` overridden |
| `unauthenticated_client` | function | AsyncClient, no auth override |
| `reset_app_state` | function (autouse) | Clears `dependency_overrides` before/after |

### Integration (`tests/integration/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `test_user` | function | User created in DB for the current test |
| `authenticated_client` | function | `client` + `get_current_user → test_user` |
| `mock_agent` | function | MagicMock ChatbotAgent with AsyncMock methods |
| `authenticated_client_with_agent` | function | `authenticated_client` + `get_chatbot_agent → mock_agent` |

## Markers

```python
pytestmark = pytest.mark.unit        # every unit test file
pytestmark = pytest.mark.integration # every integration test file

@pytest.mark.slow  # external API calls (skipped in CI fast mode)
```

## Coverage

```bash
APP_ENV=test uv run pytest tests/unit -m unit --cov=app --cov-report=term-missing
APP_ENV=test uv run pytest tests/integration -m integration --cov=app --cov-report=html
open htmlcov/index.html
```
