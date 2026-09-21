""" ORM model for custom agent definitions. """

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class AgentRow(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_agents_user_name"),)

    # Surrogate primary key (uuid4 hex). The natural key is (user_id, name),
    # enforced by the UNIQUE constraint above; a surrogate PK keeps the row
    # identity stable if an agent is ever renamed in a future revision.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    # Stored lowercase, matching the on-disk layout (Paths.user_agent_dir lowercases).
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    soul: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )