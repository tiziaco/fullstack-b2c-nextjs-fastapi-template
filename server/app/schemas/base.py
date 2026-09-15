"""Base schemas for common API responses.

This module defines Pydantic models for standardized API responses.
"""

from typing import (
    Any,
    Dict,
    Optional,
)

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standardized error response schema.

    This schema ensures all API errors return a consistent format
    with machine-readable error codes and optional detailed information.

    Attributes:
        error: Machine-readable error code (e.g., "USER_NOT_FOUND")
        message: Human-readable error description
        correlation_id: Request correlation ID for tracing
        details: Optional detailed information (e.g., field-level validation errors)
    """

    error: str
    message: str
    correlation_id: str
    details: Optional[Dict[str, Any]] = None
