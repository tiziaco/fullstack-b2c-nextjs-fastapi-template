"""Tests for app.schemas.system — the response models for /, /health and /ready."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.config import Environment
from app.schemas.system import (
    AgentStatus,
    ComponentsStatus,
    ConnectionPoolStats,
    DatabaseStatus,
    HealthResponse,
    ReadinessResponse,
    RootResponse,
)

pytestmark = pytest.mark.unit


def _components(**overrides) -> ComponentsStatus:
    defaults = dict(
        api="healthy",
        database=DatabaseStatus(
            status="healthy",
            connection_pool=ConnectionPoolStats(size=5, checked_in=5, checked_out=0, overflow=0, total=5),
        ),
        agents={"chatbot": AgentStatus(ready=True, graph_compiled=True)},
        agents_healthy=True,
    )
    defaults.update(overrides)
    return ComponentsStatus(**defaults)


class TestRootResponse:
    def test_valid(self):
        model = RootResponse(
            name="FastAPI LangGraph Clerk",
            version="1.0.0",
            status="healthy",
            environment=Environment.DEVELOPMENT,
            swagger_url="/docs",
            redoc_url="/redoc",
        )
        assert model.version == "1.0.0"


class TestHealthResponse:
    def test_valid_healthy(self):
        model = HealthResponse(status="healthy", timestamp=datetime.now(UTC))
        assert model.status == "healthy"

    def test_valid_degraded(self):
        model = HealthResponse(status="degraded", timestamp=datetime.now(UTC))
        assert model.status == "degraded"

    def test_rejects_unknown_status(self):
        with pytest.raises(ValidationError):
            HealthResponse(status="on fire", timestamp=datetime.now(UTC))


class TestComponentsStatus:
    def test_agents_is_a_mapping_of_agent_name_to_status(self):
        model = _components()
        assert model.agents["chatbot"].ready is True
        assert model.agents["chatbot"].graph_compiled is True

    def test_agents_defaults_to_empty_and_carries_an_error_string(self):
        model = _components(agents={}, agents_healthy=False, agents_error="Agents not initialized")
        assert model.agents == {}
        assert model.agents_error == "Agents not initialized"

    def test_agents_rejects_a_bare_string_value(self):
        # This is the shape that made the hand-written frontend type wrong:
        # an object on the success path, a string on the failure path.
        with pytest.raises(ValidationError):
            _components(agents={"error": "Agents not initialized"})


class TestReadinessResponse:
    def test_valid(self):
        model = ReadinessResponse(
            status="healthy",
            version="1.0.0",
            environment=Environment.DEVELOPMENT,
            components=_components(),
            timestamp=datetime.now(UTC),
        )
        assert model.components.database.connection_pool.total == 5

    def test_requires_components(self):
        with pytest.raises(ValidationError):
            ReadinessResponse(
                status="healthy",
                version="1.0.0",
                environment=Environment.DEVELOPMENT,
                timestamp=datetime.now(UTC),
            )
