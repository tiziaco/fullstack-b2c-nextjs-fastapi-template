# Exception Hierarchy

Exceptions follow a three-level hierarchy: base → category → domain-specific.

```
ServiceError (base, 500)
├── AuthenticationError (401)
├── NotFoundError (404)
├── ConflictError (409)
├── ValidationError (422)
├── DatabaseError (500)
│   ├── DatabaseConflictError (409)
│   └── DatabaseConnectionError (503)
└── [External service base] e.g. ClerkServiceError (502)
    ├── ClerkUserNotFoundError (404)
    ├── ClerkAuthenticationError (401)
    └── ClerkRateLimitError (429)
```

## Base class (`app/exceptions/base.py`)

```python
class ServiceError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, **context: Any):
        self.message = message
        self.context = context  # Merged into structured logs by the exception handler
        super().__init__(self.message)
```

## Domain exceptions (`app/services/<domain>/exceptions.py`)

```python
class PaymentNotFoundError(NotFoundError):
    """Raised when a payment is not found or does not belong to the requesting user."""
    error_code = "PAYMENT_NOT_FOUND"

class PaymentProcessingError(ServiceError):
    """Raised when the payment processor returns an unexpected error."""
    status_code = 502
    error_code = "PAYMENT_PROCESSING_ERROR"
```

## External service exceptions

Give each external service its own base class so callers can catch all errors from that service in one clause:

```python
# app/integrations/stripe/exceptions.py

class StripeServiceError(ServiceError):
    status_code = 502
    error_code = "STRIPE_ERROR"

class StripeCustomerNotFoundError(StripeServiceError):
    status_code = 404
    error_code = "STRIPE_CUSTOMER_NOT_FOUND"

class StripeAuthenticationError(StripeServiceError):
    status_code = 401
    error_code = "STRIPE_AUTH_ERROR"

class StripeRateLimitError(StripeServiceError):
    status_code = 429
    error_code = "STRIPE_RATE_LIMIT"

class StripeAPIError(StripeServiceError):
    error_code = "STRIPE_API_ERROR"
```

## Rules

- Every domain gets its own `exceptions.py` file
- Always inherit from a category class (`NotFoundError`, `ConflictError`, etc.) — only go direct to `ServiceError` if no category fits
- `error_code` is always `SCREAMING_SNAKE_CASE`
- Pass context as kwargs to the constructor — the exception handler merges them into structured logs and the error response `details` field automatically:

```json
{
  "error": "PAYMENT_NOT_FOUND",
  "message": "Payment 42 not found",
  "correlation_id": "abc-123",
  "details": {"payment_id": 42}
}
```
