"""Centralized exception handlers for FastAPI application.

This module provides handlers for domain-specific exceptions that integrate
with correlation IDs and structured logging.
"""

from asgi_correlation_id import correlation_id
from fastapi import (
    Request,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import logger
from app.core.metrics import app_exceptions_total
from app.exceptions.base import ServiceError
from app.schemas.base import ErrorResponse


async def service_exception_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Handle all ServiceError exceptions with correlation ID tracking.

    This handler catches domain-specific exceptions, logs them with structured
    context, and returns a standardized error response to the client.

    Args:
        request: The FastAPI request object
        exc: The service exception that was raised

    Returns:
        JSONResponse: Standardized error response with correlation ID
    """
    # Get correlation ID from asgi-correlation-id context
    request_correlation_id = correlation_id.get() or "unknown"

    # Build structured logging context
    log_context = {
        "correlation_id": request_correlation_id,
        "error_type": exc.__class__.__name__,
        "error_code": exc.error_code,
        "status_code": exc.status_code,
        "endpoint": request.url.path,
        "method": request.method,
        **exc.context,  # Include exception-specific context
    }

    # The status code alone cannot identify the failure: every LLM error in
    # app/services/llm/exceptions.py carries 503, so five distinct causes —
    # rate limit, timeout, streaming, fallback exhausted, generic API error —
    # collapse into one indistinguishable series without this label.
    app_exceptions_total.labels(
        error_code=exc.error_code,
        exception_type=exc.__class__.__name__,
    ).inc()

    # Log with appropriate level based on status code
    if exc.status_code >= 500:
        # Server errors - use exception() to capture full traceback
        logger.exception("service_error_5xx", **log_context)
    elif exc.status_code >= 400:
        # Client errors - use warning()
        logger.warning("service_error_4xx", **log_context)
    else:
        # Unexpected status codes
        logger.info("service_error_other", **log_context)

    # Build error response
    error_response = ErrorResponse(
        error=exc.error_code,
        message=exc.message,
        correlation_id=request_correlation_id,
        details=exc.context if exc.context else None,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors from request data.

    Args:
        request: The request that caused the validation error
        exc: The validation error

    Returns:
        JSONResponse: A formatted error response with field-specific error details
    """
    logger.error(
        "validation_error",
        client_host=request.client.host if request.client else "unknown",
        path=request.url.path,
        method=request.method,
        error_count=len(exc.errors()),
    )

    # Format the errors to be more user-friendly
    formatted_errors = []
    for error in exc.errors():
        loc = " -> ".join([str(loc_part) for loc_part in error["loc"] if loc_part != "body"])
        formatted_errors.append({"field": loc, "message": error["msg"]})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Validation error", "errors": formatted_errors},
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions globally.

    This handler catches any exception that wasn't handled by more specific
    exception handlers. It logs the error and returns a generic 500 response
    to avoid exposing internal error details to clients.

    Args:
        request: The request that caused the exception
        exc: The exception that was raised

    Returns:
        JSONResponse: A generic 500 error response
    """
    # `UNHANDLED` rather than an error_code: nothing reaching here declared one.
    # The response is a generic 500 that deliberately hides the cause from the
    # client, so `exception_type` is the only record of what actually broke
    # outside the log line.
    app_exceptions_total.labels(
        error_code="UNHANDLED",
        exception_type=exc.__class__.__name__,
    ).inc()

    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        client_host=request.client.host if request.client else "unknown",
        exception_type=exc.__class__.__name__,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )
