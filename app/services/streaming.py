from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.caption import CaptionEventModel, CaptionModel
from app.models.session import SessionModel
from app.schemas.streaming import CaptionMessage


def persist_caption_event(
    db: Session,
    session: SessionModel,
    frame_index: int,
    message: CaptionMessage,
) -> CaptionEventModel:
    existing = db.get(CaptionEventModel, message.event_id)
    if existing is not None:
        if existing.session_id != session.id:
            raise ValueError("Caption event belongs to another session.")
        if session.last_frame_index is None or frame_index > session.last_frame_index:
            session.last_frame_index = frame_index
            db.commit()
        return existing

    now = datetime.now(UTC)
    caption = CaptionModel(
        id=message.event_id,
        session_id=session.id,
        current_text=message.caption,
        version=1,
        status="VISIBLE",
        created_at=now,
        updated_at=now,
    )
    db.add(caption)
    db.flush()
    event = CaptionEventModel(
        id=message.event_id,
        session_id=session.id,
        caption_id=message.event_id,
        event_index=session.last_event_index + 1,
        timestamp_ms=message.end_ms,
        decision="EMIT",
        text=message.caption,
        caption_version=1,
        previous_event_id=None,
        model_version=message.model_id,
        is_demo=False,
        start_ms=message.start_ms,
        end_ms=message.end_ms,
        model_id=message.model_id,
        inference_ms=message.inference_ms,
        processing_delay_ms=message.processing_delay_ms,
        is_mock=message.is_mock,
        created_at=now,
    )
    db.add(event)
    session.last_event_index = event.event_index
    session.last_frame_index = frame_index
    db.add(session)
    db.commit()
    db.refresh(event)
    return event


def record_processed_frame(db: Session, session: SessionModel, frame_index: int) -> None:
    if session.last_frame_index is None or frame_index > session.last_frame_index:
        session.last_frame_index = frame_index
        db.add(session)
        db.commit()
