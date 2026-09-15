"""System health and status endpoints.

This module provides infrastructure endpoints for monitoring application health,
status, and basic information.
"""

from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.dependencies.authentication import CurrentUser
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metadata import PROJECT_NAME, VERSION
from app.database.engine import health_check as db_health_check
from app.schemas.system import (
    AgentStatus,
    ComponentsStatus,
    ConnectionPoolStats,
    DatabaseStatus,
    HealthResponse,
    ReadinessResponse,
    RootResponse,
)

router = APIRouter(tags=["system"])


@router.get(
    "/",
    operation_id="getRoot",
    response_model=RootResponse,
    summary="Get API information",
    description="Retrieve basic API metadata including version, environment, and documentation URLs.",
)
@limiter.limit(settings.rate_limits.endpoints.ROOT[0])
async def root(request: Request) -> RootResponse:
    """Root endpoint returning basic API information."""
    logger.info("root_endpoint_called")
    return RootResponse(
        name=PROJECT_NAME,
        version=VERSION,
        status="healthy",
        environment=settings.ENVIRONMENT,
        swagger_url="/docs",
        redoc_url="/redoc",
    )


@router.get(
    "/health",
    operation_id="getHealth",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "System is degraded"}},
    summary="Check API health status",
    description="Minimal public health check endpoint for container orchestration and load balancers. Returns basic status without sensitive details.",
)
@limiter.limit(settings.rate_limits.endpoints.HEALTH[0])
async def health_check(request: Request, response: Response) -> HealthResponse:
    """Minimal public health check endpoint for orchestrators and load balancers."""
    engine: AsyncEngine = request.app.state.engine
    db_healthy = await db_health_check(engine)

    agents_healthy = False
    if hasattr(request.app.state, "agents"):
        agents_healthy = all(agent.is_ready() for agent in request.app.state.agents.values())

    overall_healthy = db_healthy and agents_healthy
    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if overall_healthy else "degraded",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    operation_id="getReadiness",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "System is degraded"}},
    summary="Get detailed readiness status",
    description="Detailed readiness check with component-level health information. Requires authentication. Use this endpoint for monitoring dashboards and operational visibility.",
)
@limiter.limit(settings.rate_limits.endpoints.READY[0])
async def readiness_check(user: CurrentUser, request: Request, response: Response) -> ReadinessResponse:
    """Detailed readiness check for authenticated operations teams."""
    logger.info("readiness_check_called", user_id=user.id)

    engine: AsyncEngine = request.app.state.engine
    db_healthy = await db_health_check(engine)

    pool_stats = ConnectionPoolStats(
        size=engine.pool.size(),
        checked_in=engine.pool.checkedin(),
        checked_out=engine.pool.checkedout(),
        overflow=engine.pool.overflow(),
        total=engine.pool.size() + engine.pool.overflow(),
    )

    # `agents` keeps one shape regardless of outcome: a mapping of agent name to
    # status. The "never initialised" case is carried by agents_error, not by
    # substituting a different value type.
    agents: dict[str, AgentStatus] = {}
    agents_error: str | None = None
    agents_healthy = False

    if hasattr(request.app.state, "agents"):
        agents_healthy = True
        for agent_name, agent_instance in request.app.state.agents.items():
            is_ready = agent_instance.is_ready()
            agents[agent_name] = AgentStatus(ready=is_ready, graph_compiled=is_ready)
            if not is_ready:
                agents_healthy = False
    else:
        agents_error = "Agents not initialized"

    overall_healthy = db_healthy and agents_healthy
    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="healthy" if overall_healthy else "degraded",
        version=VERSION,
        environment=settings.ENVIRONMENT,
        components=ComponentsStatus(
            api="healthy",
            database=DatabaseStatus(
                status="healthy" if db_healthy else "unhealthy",
                connection_pool=pool_stats,
            ),
            agents=agents,
            agents_healthy=agents_healthy,
            agents_error=agents_error,
        ),
        timestamp=datetime.now(UTC),
    )
