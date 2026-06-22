"""
app/models/user.py
──────────────────
SQLAlchemy ORM model for regular platform users (teenagers / PWDs).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class DisabilityType(str, enum.Enum):
    NONE = "none"
    VISUAL = "visual"
    HEARING = "hearing"
    COGNITIVE = "cognitive"
    PHYSICAL = "physical"
    OTHER = "other"


class User(Base):
    __tablename__ = "users"

    # ── Primary key ──────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Identity ─────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Profile ──────────────────────────────────────────────
    full_name: Mapped[str | None] = mapped_column(String(150))
    age: Mapped[int | None] = mapped_column()           # for content gating
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en"                        # "en" | "rw"
    )
    disability_type: Mapped[DisabilityType] = mapped_column(
        Enum(DisabilityType), default=DisabilityType.NONE
    )

    # ── Access control ───────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Auth tokens ──────────────────────────────────────────
    refresh_token: Mapped[str | None] = mapped_column(Text)

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role}>"
