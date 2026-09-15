"""CORS middleware configuration for FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger


def setup_cors(app: FastAPI) -> None:
    """Set up CORS middleware with configuration from settings.

    Configures Cross-Origin Resource Sharing (CORS) to allow requests from
    specified origins. Origins are configured via environment variables and
    read from settings.ALLOWED_ORIGINS.

    Args:
        app: FastAPI application instance
    """
    logger.debug(
        "initializing_cors_middleware",
        allowed_origins=settings.cors.ALLOWED_ORIGINS,
        environment=settings.ENVIRONMENT.value,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Accept",
            "Origin",
            "Cache-Control",
            "Pragma",
            "Expires",
            "X-Request-ID",
        ],
        expose_headers=[
            "Content-Length",
            "X-Total-Count",
            "X-Request-ID",
        ],
        max_age=3600,  # Cache preflight requests for 1 hour
    )

    logger.info(
        "cors_middleware_initialized",
        origins_count=len(settings.cors.ALLOWED_ORIGINS),
    )
