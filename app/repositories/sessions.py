from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.session import SessionModel
from app.schemas.contracts import SessionCreateRequest, SessionMode, SessionStatus


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: SessionCreateRequest, model_version: str) -> SessionModel:
        now = datetime.now(UTC)
        session = SessionModel(
            id=str(uuid4()),
            source=payload.source,
            mode=payload.mode,
            status=SessionStatus.ACTIVE,
            scenario_id=payload.scenario_id,
            model_version=model_version,
            created_at=now,
            started_at=now,
            last_frame_index=None,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get(self, session_id: str) -> SessionModel | None:
        return self.db.get(SessionModel, session_id)

    def list(
        self,
        status: SessionStatus | None,
        mode: SessionMode | None,
        limit: int,
        offset: int,
    ) -> tuple[list[SessionModel], int]:
        statement = select(SessionModel)
        count_statement = select(func.count()).select_from(SessionModel)
        if status is not None:
            statement = statement.where(SessionModel.status == status)
            count_statement = count_statement.where(SessionModel.status == status)
        if mode is not None:
            statement = statement.where(SessionModel.mode == mode)
            count_statement = count_statement.where(SessionModel.mode == mode)
        statement = statement.order_by(SessionModel.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(statement)), int(self.db.scalar(count_statement) or 0)

    def update_status(self, session: SessionModel, status: SessionStatus) -> SessionModel:
        session.status = status
        if status in {SessionStatus.COMPLETED, SessionStatus.FAILED} and session.ended_at is None:
            session.ended_at = datetime.now(UTC)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_last_frame(self, session: SessionModel, frame_index: int) -> None:
        session.last_frame_index = frame_index
        self.db.add(session)
        self.db.commit()
