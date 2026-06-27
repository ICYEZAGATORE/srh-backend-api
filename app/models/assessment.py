"""
app/models/assessment.py — Pre/post SRH knowledge assessment submissions.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("type IN ('pre', 'post')", name="ck_assessment_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sessions.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(10))  # 'pre' | 'post'
    # List of {"question_id": ..., "answer": ...} dicts.
    responses: Mapped[list | dict | None] = mapped_column(JSONType, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("Session", back_populates="assessments")

    def __repr__(self) -> str:
        return f"<Assessment {self.id} type={self.type}>"
