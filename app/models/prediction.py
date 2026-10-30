from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.schemas.contracts import Decision

if TYPE_CHECKING:
    from app.models.session import SessionModel


class PredictionModel(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_label: Mapped[str] = mapped_column(String(256), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[Decision] = mapped_column(Enum(Decision), nullable=False, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_prediction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    inference_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    session: Mapped[SessionModel] = relationship(back_populates="predictions")
