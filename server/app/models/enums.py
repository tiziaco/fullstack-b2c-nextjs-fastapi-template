"""Domain enumerations for the application."""

from enum import StrEnum


class Role(StrEnum):
    """Platform roles.

    Sourced from Clerk `publicMetadata.role` and delivered as a custom `role`
    claim on the session token. AuthMiddleware reads the claim; get_current_role
    validates it against this enum.

    Platform roles only. A per-resource capability — group moderator, page
    admin, recruiter — is not a role: it is scoped to a resource, non-exclusive
    and revocable, and a single-valued claim expresses none of the three. Model
    those as rows and check them per resource.

    Migration note: when switching auth providers, only AuthMiddleware and
    get_current_role change. This enum and all consumers remain unchanged.
    """

    USER = "user"
    ADMIN = "admin"
