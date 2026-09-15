"""This file contains the main application entry point."""

import os
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from langfuse import Langfuse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.middlewares import (
    AccessLogMiddleware,
    AuthMiddleware,
    LoggingContextMiddleware,
    SecurityHeadersMiddleware,
    setup_cors,
    setup_metrics,
)
from app.api.system import router as system_router
from app.api.v1.api import api_router
from app.core.config import Environment, settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metadata import API_V1_STR, DESCRIPTION, PROJECT_NAME, VERSION
from app.database.engine import (
    close_database_engine,
    create_session_factory,
    initialize_database_engine,
)
from app.exceptions import (
    global_exception_handler,
    service_exception_handler,
    validation_exception_handler,
)
from app.exceptions.base import ServiceError

# Load environment variables
load_dotenv()

# Initialize Langfuse
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    from app.agents.factory import initialize_agents
    from app.agents.shared.checkpointing.postgres import (
        close_connection_pool,
        create_postgres_saver,
    )

    logger.info(
        "application_startup",
        project_name=PROJECT_NAME,
        version=VERSION,
        api_prefix=API_V1_STR,
    )

    # Initialize database
    engine = await initialize_database_engine()
    session_factory = create_session_factory(engine)

    # Initialize checkpointer once at startup
    checkpointer = await create_postgres_saver()
    logger.info("checkpointer_initialized_at_startup")

    # Initialize all agents with pre-compiled graphs
    agents = await initialize_agents(checkpointer)
    logger.info("application_ready", agent_names=list(agents.keys()))

    # Store in app state for dependency injection
    app.state.limiter = limiter
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.agents = agents

    yield

    # Cleanup
    await close_connection_pool()
    await close_database_engine(engine)
    logger.info("application_shutdown")


_is_production = settings.ENVIRONMENT == Environment.PRODUCTION

app = FastAPI(
    # Code-owned, never settings-derived — see app/core/metadata.py.
    title=PROJECT_NAME,
    version=VERSION,
    description=DESCRIPTION,
    openapi_url=None if _is_production else f"{API_V1_STR}/openapi.json",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/oauth2-redirect",
    swagger_ui_init_oauth={
        "clientId": settings.auth.OAUTH_CLIENT_ID,
        "scopes": "openid profile email offline_access",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

# Set up Prometheus metrics (instruments the app and exposes /metrics)
setup_metrics(app)

# Add logging context middleware (binds clerk_id to logging context)
app.add_middleware(LoggingContextMiddleware)

# Add auth middleware (extracts and verifies JWT tokens, sets request.state.clerk_id)
app.add_middleware(AuthMiddleware)

# Add HTTP access logging middleware (captures request/response details with correlation ID)
app.add_middleware(AccessLogMiddleware)

# Set up CORS middleware (added before CorrelationIdMiddleware so it executes after)
setup_cors(app)

# Add correlation ID middleware (must be added last so it executes first and generates ID for all subsequent middleware)
app.add_middleware(CorrelationIdMiddleware)

# Add security headers middleware (outermost layer so headers are applied to every response)
app.add_middleware(SecurityHeadersMiddleware)

# Set up exception handlers (order matters: most specific first)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ServiceError, service_exception_handler)  # Domain exceptions
app.add_exception_handler(Exception, global_exception_handler)  # Catch-all


# Include routers
app.include_router(system_router)  # System endpoints at root level
app.include_router(api_router, prefix=API_V1_STR)  # Versioned API endpoints
