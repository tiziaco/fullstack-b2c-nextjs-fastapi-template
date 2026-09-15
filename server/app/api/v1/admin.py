"""Administrative endpoints.

Ships one endpoint deliberately: it is the worked example of `AdminOnly` and
the only production route that exercises the role seam end to end. Replace or
extend it with real administrative endpoints; do not delete the guard.

A real admin route that also touches the DB must take `CurrentUser` as well —
`AdminOnly` alone never provisions the user, so `request.state.user_id` stays
`None`.
"""

from fastapi import APIRouter

from app.api.dependencies.authorization import AdminOnly

router = APIRouter()


@router.get(
    "/ping",
    operation_id="adminPing",
    summary="Admin-only smoke endpoint",
    description="Returns 200 for a caller whose role is `admin`, 403 otherwise. "
    "Exists to verify the role claim, the middleware and require_role() end to end.",
    dependencies=[AdminOnly],
)
async def admin_ping() -> dict[str, bool]:
    """Confirm the caller holds the admin platform role."""
    return {"ok": True}
