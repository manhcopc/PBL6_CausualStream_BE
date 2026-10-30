from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.schemas.contracts import SessionMode, SessionSource, SessionStatus

if TYPE_CHECKING:
    from app.models.prediction import PredictionModel


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[SessionSource] = mapped_column(Enum(SessionSource), nullable=False)
    mode: Mapped[SessionMode] = mapped_column(Enum(SessionMode), nullable=False, index=True)
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), nullable=False, index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    demo_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_index: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)

    predictions: Mapped[list[PredictionModel]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
