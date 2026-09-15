"""Response schemas for the system endpoints (/, /health, /ready).

These models are the contract for the frontend's server-status widget. Before
they existed the three routes were annotated `Dict[str, Any]`, which emits
`additionalProperties: true` into the OpenAPI schema and generates
`{[key: string]: unknown}` on the client — type safety erased silently.
"""

from datetime import datetime
from typing import (
    Dict,
    Literal,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
)

from app.core.config import Environment


class ConnectionPoolStats(BaseModel):
    """SQLAlchemy connection pool counters."""

    size: int = Field(..., description="Configured pool size")
    checked_in: int = Field(..., description="Connections idle in the pool")
    checked_out: int = Field(..., description="Connections currently in use")
    overflow: int = Field(..., description="Connections created beyond the pool size")
    total: int = Field(..., description="size + overflow")


class DatabaseStatus(BaseModel):
    """Database connectivity and pool state."""

    status: Literal["healthy", "unhealthy"] = Field(..., description="Database reachability")
    connection_pool: ConnectionPoolStats = Field(..., description="Pool counters")


class AgentStatus(BaseModel):
    """Readiness of a single agent."""

    ready: bool = Field(..., description="Agent reports itself ready")
    graph_compiled: bool = Field(..., description="LangGraph graph is compiled")


class ComponentsStatus(BaseModel):
    """Per-component readiness detail.

    `agents` is always a mapping of agent name to status — never a bare string,
    and never wrapped in an envelope. The "agents were never initialised"
    condition is carried by `agents_error`, so the value's shape does not
    depend on the outcome.
    """

    api: Literal["healthy"] = Field(..., description="The API itself is serving")
    database: DatabaseStatus = Field(..., description="Database component")
    agents: Dict[str, AgentStatus] = Field(default_factory=dict, description="Agent name to readiness status")
    agents_healthy: bool = Field(..., description="Every registered agent is ready")
    agents_error: Optional[str] = Field(None, description="Set when the agent registry was never initialised")


class RootResponse(BaseModel):
    """Basic API metadata returned by GET /."""

    name: str = Field(..., description="Project name")
    version: str = Field(..., description="Application version")
    status: Literal["healthy"] = Field(..., description="Always healthy if this responds")
    environment: Environment = Field(..., description="Deployment environment")
    swagger_url: str = Field(..., description="Path to the Swagger UI")
    redoc_url: str = Field(..., description="Path to the ReDoc UI")


class HealthResponse(BaseModel):
    """Minimal public health check returned by GET /health."""

    status: Literal["healthy", "degraded"] = Field(..., description="Overall health")
    timestamp: datetime = Field(..., description="When the check ran")


class ReadinessResponse(BaseModel):
    """Detailed authenticated readiness returned by GET /ready."""

    status: Literal["healthy", "degraded"] = Field(..., description="Overall readiness")
    version: str = Field(..., description="Application version")
    environment: Environment = Field(..., description="Deployment environment")
    components: ComponentsStatus = Field(..., description="Per-component detail")
    timestamp: datetime = Field(..., description="When the check ran")
