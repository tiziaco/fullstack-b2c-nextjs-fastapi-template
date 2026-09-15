"""Base models and mixins for all models."""

from datetime import (
    UTC,
    datetime,
)
from typing import Optional

from sqlalchemy import (
    DateTime,
)
from sqlmodel import (
    Field,
    SQLModel,
)


class TimestampMixin(SQLModel):
    """created_at, set once; updated_at, refreshed on every modification."""

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,  # Often used in queries (recent records, date filters)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )


class SoftDeleteMixin(SQLModel):
    """Mixin for soft delete functionality.

    Not GDPR-compliant for personal data: the right to erasure requires the data
    actually be gone. Use this only for rows that must be retained — internal
    operational records, business records kept for legal or tax reasons,
    aggregated stats. For user accounts and user-generated content, hard delete
    and use AnonymizableMixin below.
    """

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        index=True,  # Queries often filter by deleted_at IS NULL
    )

    @property
    def is_deleted(self) -> bool:
        """Check if the record is soft deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        """Restore a soft deleted record."""
        self.deleted_at = None


class AnonymizableMixin(SQLModel):
    """Mixin for GDPR-compliant data anonymization.

    The erasure path for personal data: clear the personal fields, keep the row
    id so foreign keys stay valid, and stamp ``anonymized_at``. Satisfies the
    right to erasure while preserving business records and non-personal
    analytics.
    """

    anonymized_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_anonymized(self) -> bool:
        """Check if the record has been anonymized."""
        return self.anonymized_at is not None

    def mark_anonymized(self) -> None:
        """Mark the record as anonymized (after clearing personal data)."""
        self.anonymized_at = datetime.now(UTC)


class BaseModel(TimestampMixin, SQLModel):
    """Base for all models: created_at / updated_at tracking.

    Compose with SoftDeleteMixin or AnonymizableMixin as needed.
    """

    pass
