"""Authorization dependencies — role guards only.

Resource-ownership checks live in the service layer. Deps in this module
are stateless and do NOT touch the database.
"""

from fastapi import Depends

from app.api.dependencies.authentication import get_current_role
from app.exceptions.base import AuthorizationError
from app.models.enums import Role


def require_role(*allowed: Role):
    """Dependency factory that enforces one of the allowed roles.

    Usage:
        @router.get("/admin/ping", dependencies=[AdminOnly])
        async def admin_ping(): ...

    Args:
        *allowed: One or more Role values that are permitted.

    Returns:
        A FastAPI Depends object suitable for use in the dependencies list.
    """

    def dependency(role: Role = Depends(get_current_role)) -> None:
        if role not in allowed:
            raise AuthorizationError(f"Role '{role}' is not permitted. Required: {[r.value for r in allowed]}")

    return Depends(dependency)


# ---------------------------------------------------------------------------
# Role guards — use in endpoint `dependencies=[...]` list
# ---------------------------------------------------------------------------

# Platform administrators only
AdminOnly = require_role(Role.ADMIN)
