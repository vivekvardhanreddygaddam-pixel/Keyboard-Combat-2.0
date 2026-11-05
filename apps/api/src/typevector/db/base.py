"""TypeVector Arena — SQLAlchemy Declarative Base, Naming Conventions, and Mixins."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Strict PostgreSQL naming convention for unambiguous constraint, index, and key naming
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base class for all TypeVector Arena models."""

    metadata = metadata


class UUIDPrimaryKeyMixin:
    """Mixin adding a standard UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,
    )


class TimestampMixin:
    """Mixin adding timezone-aware UTC creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
    )


class OptimisticLockMixin:
    """Mixin adding an integer version counter for optimistic concurrency control."""

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        sort_order=99,
    )
