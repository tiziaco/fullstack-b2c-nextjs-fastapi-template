# Error Handling

## Fail Fast on Missing Resources

Raise immediately when a resource doesn't exist. Never return `None` from a service — the caller shouldn't have to null-check.

```python
result = await db.execute(stmt)
record = result.scalar_one_or_none()
if not record:
    raise RecordNotFoundError(
        f"Record {record_id} not found",
        record_id=record_id,
    )
return record
```

## Translating External API Errors

When calling third-party services, catch their low-level errors and translate them to domain exceptions. Always `raise ... from e` to preserve the original traceback.

```python
try:
    result = external_client.do_something(resource_id)
except ExternalNotFoundError as e:
    raise DomainNotFoundError("...", resource_id=resource_id) from e
except ExternalRateLimitError as e:
    raise DomainRateLimitError("...", resource_id=resource_id) from e
except ExternalError as e:
    raise DomainAPIError(f"Unexpected error: {e}", resource_id=resource_id) from e
```

## Retry with Exponential Backoff

For transient failures on external calls, use `tenacity`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    before_sleep=before_sleep_log(logger, "WARNING"),
    reraise=True,
)
async def _call_with_retry(self, ...):
    ...
```

If you have multiple fallback targets (e.g., multiple LLM models), rotate through all of them before raising a `FallbackExhaustedError`.

## Database Error Handling

See `references/database.md` for the full DB error handling and race condition patterns.
