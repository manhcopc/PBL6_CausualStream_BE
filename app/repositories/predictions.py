from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.prediction import PredictionModel
from app.schemas.contracts import PredictionResponse


class PredictionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_from_response(self, prediction: PredictionResponse) -> PredictionModel:
        record = PredictionModel(
            id=prediction.prediction_id,
            session_id=prediction.session_id,
            frame_index=prediction.frame_index,
            timestamp_ms=prediction.timestamp_ms,
            action_id=prediction.action_id,
            action_label=prediction.action_label,
            confidence=prediction.confidence,
            decision=prediction.decision,
            message=prediction.message,
            previous_prediction_id=prediction.previous_prediction_id,
            model_version=prediction.model_version,
            inference_time_ms=prediction.inference_time_ms,
            is_demo=prediction.is_demo,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_for_session(
        self, session_id: str, limit: int, offset: int
    ) -> tuple[list[PredictionModel], int]:
        statement = (
            select(PredictionModel)
            .where(PredictionModel.session_id == session_id)
            .order_by(PredictionModel.timestamp_ms.asc(), PredictionModel.frame_index.asc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = (
            select(func.count())
            .select_from(PredictionModel)
            .where(PredictionModel.session_id == session_id)
        )
        return list(self.db.scalars(statement)), int(self.db.scalar(count_statement) or 0)
