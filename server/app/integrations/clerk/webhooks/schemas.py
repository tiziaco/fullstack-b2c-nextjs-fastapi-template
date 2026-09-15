"""Clerk webhook envelope, and what verification and dispatch pass along.

Every Clerk webhook shares one shape: a `type` discriminator, a `data`
payload whose contents depend on the type, and delivery metadata. Payload
bodies are left as dicts rather than modelled per event — Clerk adds fields
without notice, and a strict model would reject deliveries for additions we
do not read.

The two dataclasses below live here, rather than in the modules that build
them, so `verification` and `dispatcher` never have to import each other —
the route composes them.
"""

from dataclasses import dataclass
from typing import (
    Any,
    Optional,
)

from pydantic import (
    BaseModel,
    ConfigDict,
)
from sqlalchemy.ext.asyncio import AsyncSession


class ClerkEvent(BaseModel):
    """A verified Clerk webhook event."""

    model_config = ConfigDict(extra="ignore")

    type: str
    data: dict[str, Any]
    timestamp: Optional[int] = None
    instance_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    """A Clerk event whose signature has been checked, plus its delivery id."""

    event: ClerkEvent
    message_id: str


@dataclass(frozen=True, slots=True)
class WebhookContext:
    """Everything a handler is given for one delivery.

    Per-delivery facts only. Process-wide capabilities (an agent, a service
    singleton) are not passed here — handlers that need one import it, the
    way every other module in this codebase reaches a singleton.
    """

    event: ClerkEvent
    message_id: str
    session: AsyncSession

    @property
    def data(self) -> dict[str, Any]:
        """The event payload — the part nearly every handler wants."""
        return self.event.data
