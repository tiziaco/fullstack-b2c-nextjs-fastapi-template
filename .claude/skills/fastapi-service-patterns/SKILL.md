---
name: fastapi-service-patterns
description: >
  Coding patterns and conventions for this FastAPI project. Use whenever creating or modifying a service class,
  defining custom exceptions, adding error handling, writing API routes, or wrapping business logic around
  FastAPI endpoints, or integrating a third-party provider in either direction. Trigger on tasks like
  "add a service", "create an exception", "add an endpoint", "handle this error", "add a new route",
  "implement a repository", "wrap this SDK", "handle a webhook", or any feature work touching
  app/services/, app/integrations/, app/api/, or app/exceptions/. Use even for partial tasks like "add a method to XService" —
  always follow the patterns below.
---

# FastAPI Service Patterns

This project has consistent patterns across services, exceptions, and API routes. Read the relevant reference file before writing any code.

## Reference files

| Topic | File | Read when… |
|---|---|---|
| Service classes | `references/services.md` | Adding/modifying a service or its methods |
| Exceptions | `references/exceptions.md` | Defining new exception classes |
| Error handling | `references/error-handling.md` | Writing try/catch, retries, or fail-fast checks |
| External API adapters | `references/client-wrappers.md` | Wrapping a third-party SDK or HTTP client (outbound) |
| Inbound webhooks | `references/webhooks.md` | Receiving events a provider pushes to us (signature, dispatch, handlers) |
| API routes | `references/api-routes.md` | Adding endpoints, pagination, batch ops, or deletes |
| Database operations | `references/database.md` | Querying, bulk ops, relationship loading, N+1 avoidance |

## Quick rules (always apply)

- Services: stateless orchestrator class + `@staticmethod async` methods + module-level singleton
- Services never touch the DB directly — all `select()`/`db.execute()` calls live in a `repository.py`, which is
  also a stateless class + `@staticmethod async` methods + module-level singleton
- A service can orchestrate more than one repository and/or external client wrapper — that's its job
- Never return `None` from a service — raise a domain exception instead
- Every domain has its own `exceptions.py`; always inherit from a category class
- `raise ... from e` on every external error to preserve the traceback
- `flush()` + `refresh()` after DB writes — never `commit()` (the session dep handles that)
- `request: Request` is always the first route param (required by the rate limiter)
- `@limiter.limit(...)` on every route
- Structured logging: `logger.info("snake_case_event", key=value)` — never f-strings
- Soft-delete only: set `deleted_at`, never `DELETE` from the table

## File layout for a new domain

```
app/
  services/
    payment/
      __init__.py
      service.py       # PaymentService class (orchestrator) + payment_service singleton
      repository.py    # PaymentRepository class (DB ops) + payment_repository singleton
      exceptions.py    # Domain-specific exception classes
  api/
    v1/
      payments.py      # APIRouter with route handlers
```

An external-API adapter lives in `app/integrations/<provider>/`, not `app/services/` — and has no
`repository.py`. It has `client.py` (SDK wrapper + error translation) and `exceptions.py`, plus `webhooks/` if the
provider pushes events to us. See `references/client-wrappers.md` for the outbound half and
`references/webhooks.md` for the inbound one.

Register the router in `app/api/v1/api.py`.
