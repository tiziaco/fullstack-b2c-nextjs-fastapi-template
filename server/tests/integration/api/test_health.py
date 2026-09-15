"""Integration tests for system health endpoints — /, /health, /ready."""

import pytest

pytestmark = pytest.mark.integration


class TestRootEndpoint:
    """Tests for GET /"""

    async def test_returns_200(self, unauthenticated_client):
        response = await unauthenticated_client.get("/")
        assert response.status_code == 200

    async def test_response_schema(self, unauthenticated_client):
        response = await unauthenticated_client.get("/")
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data
        assert "environment" in data
        assert data["status"] == "healthy"

    async def test_swagger_url_in_response(self, unauthenticated_client):
        response = await unauthenticated_client.get("/")
        data = response.json()
        assert "swagger_url" in data


class TestHealthEndpoint:
    """Tests for GET /health"""

    async def test_returns_valid_status_code(self, unauthenticated_client):
        response = await unauthenticated_client.get("/health")
        assert response.status_code in [200, 503]

    async def test_response_has_status_and_timestamp(self, unauthenticated_client):
        response = await unauthenticated_client.get("/health")
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] in ["healthy", "degraded"]

    async def test_degraded_without_agents(self, unauthenticated_client):
        """Health is degraded when agents aren't initialized (test environment)."""
        response = await unauthenticated_client.get("/health")
        data = response.json()
        # In tests, agents are never initialized → always degraded
        assert data["status"] == "degraded"
        assert response.status_code == 503


class TestReadyEndpoint:
    """Tests for GET /ready"""

    async def test_requires_auth_returns_401(self, client):
        response = await client.get("/ready")
        assert response.status_code == 401

    async def test_with_auth_returns_status(self, authenticated_client):
        response = await authenticated_client.get("/ready")
        # 200 or 503 — agents won't be ready but endpoint should respond
        assert response.status_code in [200, 503]

    async def test_with_auth_response_has_components(self, authenticated_client):
        response = await authenticated_client.get("/ready")
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "version" in data
        assert "environment" in data

    async def test_agents_is_a_mapping_when_not_initialized(self, authenticated_client):
        """`agents` keeps one type on every path.

        It used to be polymorphic: a mapping of agent statuses on success, a
        mapping carrying a bare "error" string when the registry was never
        initialized, and a {"status": ..., "details": ...} envelope on the
        unhealthy path. A client could not type it. Agents are never
        initialized in the test environment, so this exercises the branch that
        used to substitute a different shape.
        """
        response = await authenticated_client.get("/ready")
        agents = response.json()["components"]["agents"]
        assert isinstance(agents, dict)
        assert all(
            isinstance(status, dict) and "ready" in status and "graph_compiled" in status for status in agents.values()
        )

    async def test_agents_failure_is_reported_outside_the_agents_mapping(self, authenticated_client):
        """The not-initialized message lives in agents_error, not inside agents."""
        components = (await authenticated_client.get("/ready")).json()["components"]
        assert components["agents_error"] == "Agents not initialized"
        assert components["agents_healthy"] is False
        # The old shapes, explicitly: an "error" key smuggled into the mapping,
        # and the status/details envelope that replaced the mapping wholesale.
        assert "error" not in components["agents"]
        assert "details" not in components["agents"]
        assert "status" not in components["agents"]
