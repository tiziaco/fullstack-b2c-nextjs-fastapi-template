# Client Wrapper Services (External API Adapters)

## Folder placement

**Third-party code lives in `app/integrations/<provider>/`, never in `app/services/`.**

The two trees answer different questions. `app/services/` holds *domain* logic — the things this product would do
under any vendor (`user/`, `conversation/`, `llm/`). `app/integrations/` holds code that exists **only because a
third party does**: if you dropped the vendor, the folder would disappear with it.

One package per provider, carrying **both directions of traffic** — the outbound API we call and the inbound
webhooks they call us with:

```
app/integrations/clerk/
├── __init__.py            # exports the client + its exceptions
├── client.py              # outbound: SDK wrapper + error translation
├── exceptions.py          # the provider's exception hierarchy
├── timestamps.py          # provider-shaped helpers (Clerk's ms-epoch format)
└── webhooks/              # inbound
    ├── verification.py    # signature check -> VerifiedEvent
    ├── schemas.py         # the event envelope and what handlers receive
    ├── dispatcher.py      # event type -> handler registry
    └── handlers/          # translate each event into domain calls
```

Keeping both directions together is the point: everything that changes when the vendor changes its API sits under
one directory. Nothing in `app/integrations/` should be imported by another integration.

**The rest of this file covers the outbound half only.** For the inbound half — signature verification, the dispatch
registry, handler idempotency and ordering — see `references/webhooks.md`.

### `client.py` and `service.py`

Start with **one `client.py`** that wraps the SDK *and* translates its errors into `exceptions.py` — that is what
`app/integrations/clerk/client.py` does, and for a provider surface of a handful of calls the second file earns
nothing.

Split orchestration out into a `service.py` when it appears: multi-call sequences, retry/compensation logic, or
caching that shouldn't sit next to the SDK plumbing. At that point `client.py` keeps the raw calls and transport
errors, `service.py` composes them and owns the domain exception mapping, and it becomes the only thing other
domains import — mirroring the `repository.py` / `service.py` split in `references/services.md`, where `client.py`
is a repository for an external system instead of the database.

Don't nest a provider under a domain (`app/services/payment/stripe/`). Even an adapter used by exactly one domain
today accretes webhooks, admin tooling and auth edge cases, and the vendor/domain boundary is what makes the
codebase legible.

## `client.py` — raw SDK wrapper

**Prefer the provider's official SDK when one exists** (Stripe → `stripe-python`, Clerk → `clerk-backend-api`, etc.)
— wrap that in `client.py`. Reach for a raw `httpx.AsyncClient` only when no official SDK exists, or the SDK doesn't
support async. Official SDKs already handle auth signing, retries, pagination, and typed models — rolling your own
`httpx` wrapper around them just reimplements that worse.

Use a **stateful class with instance methods** (not static) because it holds an initialized client. Use a lazy
`@property` so the client is created on first use, not at import time.

```python
# app/integrations/stripe/client.py

class StripeClient:
    """Owns the Stripe SDK client. No domain exception translation here —
    that's StripeService's job."""

    def __init__(self):
        self._client: Optional[_StripeSDKClient] = None

    @property
    def client(self) -> _StripeSDKClient:
        """Lazy-initialize the Stripe client on first use."""
        if self._client is None:
            self._client = _StripeSDKClient(api_key=settings.stripe.SECRET_KEY.get_secret_value())
        return self._client

    def get_customer(self, customer_id: str) -> StripeCustomer:
        return self.client.customers.retrieve(customer_id)

    def delete_customer(self, customer_id: str) -> None:
        self.client.customers.delete(customer_id)


stripe_client = StripeClient()
```

## `service.py` — orchestration + error translation

```python
# app/integrations/stripe/service.py

class StripeService:
    """Anti-corruption layer over StripeClient — the only thing other domains import."""

    def get_customer(self, customer_id: str) -> StripeCustomer:
        try:
            customer = stripe_client.get_customer(customer_id)
            logger.debug("stripe_customer_fetched", customer_id=customer_id)
            return customer

        except stripe.error.InvalidRequestError as e:
            if e.http_status == 404:
                logger.warning("stripe_customer_not_found", customer_id=customer_id)
                raise StripeCustomerNotFoundError(
                    f"Customer {customer_id} not found",
                    customer_id=customer_id,
                ) from e
            raise StripeAPIError(f"Stripe request error: {e}", customer_id=customer_id) from e

        except stripe.error.AuthenticationError as e:
            logger.error("stripe_authentication_failed")
            raise StripeAuthenticationError("Stripe authentication failed") from e

        except stripe.error.RateLimitError as e:
            logger.warning("stripe_rate_limit_exceeded", customer_id=customer_id)
            raise StripeRateLimitError("Stripe rate limit exceeded", customer_id=customer_id) from e

        except Exception as e:
            logger.exception("stripe_unexpected_error", customer_id=customer_id, error=str(e))
            raise StripeAPIError(f"Unexpected Stripe error: {e}", customer_id=customer_id) from e

    def delete_customer(self, customer_id: str) -> None:
        try:
            stripe_client.delete_customer(customer_id)
            logger.info("stripe_customer_deleted", customer_id=customer_id)
        except stripe.error.InvalidRequestError as e:
            if e.http_status == 404:
                return  # Already gone — idempotent delete, not an error
            raise StripeAPIError(f"Stripe request error: {e}", customer_id=customer_id) from e
        except Exception as e:
            logger.exception("stripe_unexpected_error_on_delete", customer_id=customer_id, error=str(e))
            raise StripeAPIError(f"Unexpected Stripe error: {e}", customer_id=customer_id) from e


stripe_service = StripeService()
```

Other domains (e.g. `PaymentService.checkout()` in `references/services.md`) import and call `stripe_service`, never
`stripe_client` directly — same rule as never bypassing a repository to call `db.execute()` from a service.

## Rules

- Live under `app/integrations/<provider>/` — `app/services/` is for domain logic only
- With one file, `client.py` wraps the SDK and translates every SDK/HTTP error into `exceptions.py`
- Once `service.py` exists, `client.py` drops to raw calls only and `service.py` becomes the sole import surface for
  other domains
- `@property` for lazy client init on `client.py` — never instantiate SDK clients at module load time (config may
  not be ready)
- Instance methods, not `@staticmethod`, on both classes — they hold `_client` / no-state-but-still-instance
  patterns consistently; `service.py` stays a plain instance too for symmetry with `client.py`
- Always `raise ... from e` to preserve the original traceback
- Map each HTTP status code to a specific domain exception; fall through to the service's generic base exception
- Always include a bare `except Exception` as the last clause to prevent SDK internals from leaking
- **Idempotent deletes**: 404 on delete means "already gone" — return silently, don't raise
- Keep methods synchronous if the SDK is sync; use `asyncio.to_thread()` at the call site when calling from async
  code:

```python
# In an async service or provider:
clerk_user = await asyncio.to_thread(clerk_client.get_user, clerk_id)
```
