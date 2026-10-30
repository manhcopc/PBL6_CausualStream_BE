from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.caption import CaptionEventModel, CaptionModel
from app.models.session import SessionModel
from app.schemas.contracts import CaptionDecision, CaptionEventResponse, SessionMode, SessionStatus

DEMO_MODEL_VERSION = "demo-caption-v1"
DEMO_SCENARIOS: dict[str, tuple[tuple[CaptionDecision, int, str | None], ...]] = {
    "cup_interaction": (
        (CaptionDecision.WAIT, 0, None),
        (CaptionDecision.EMIT, 1200, "Người dùng đang nhấc chiếc cốc."),
        (CaptionDecision.REVISE, 2400, "Người dùng đang đưa chiếc cốc về phía bàn."),
        (CaptionDecision.WITHDRAW, 3600, None),
    ),
}


def demo_event_id(session_id: str, cursor: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"causalstream:demo:event:{session_id}:{cursor}"))


def demo_caption_id(session_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"causalstream:demo:caption:{session_id}"))


def event_response(event: CaptionEventModel) -> CaptionEventResponse:
    return CaptionEventResponse(
        event_id=event.id,
        session_id=event.session_id,
        event_index=event.event_index,
        timestamp_ms=event.timestamp_ms,
        decision=event.decision,
        caption_id=event.caption_id,
        text=event.text,
        caption_version=event.caption_version,
        previous_event_id=event.previous_event_id,
        model_version=event.model_version,
        is_demo=event.is_demo,
        start_ms=event.start_ms,
        end_ms=event.end_ms,
        model_id=event.model_id,
        inference_ms=event.inference_ms,
        processing_delay_ms=event.processing_delay_ms,
        is_mock=event.is_mock,
        created_at=event.created_at,
    )


def advance_demo(db: Session, session: SessionModel, expected_cursor: int) -> CaptionEventResponse:
    if session.mode != SessionMode.DEMO or session.scenario_id not in DEMO_SCENARIOS:
        raise AppError("INVALID_SESSION_MODE", "Only known DEMO sessions can be advanced.", 409)

    scenario = DEMO_SCENARIOS[session.scenario_id]
    if expected_cursor < session.demo_cursor:
        if expected_cursor >= len(scenario):
            raise AppError("SCENARIO_COMPLETED", "Demo scenario has ended.", 409)
        event = db.scalar(
            select(CaptionEventModel).where(
                CaptionEventModel.session_id == session.id,
                CaptionEventModel.event_index == expected_cursor,
            )
        )
        if event is not None:
            return event_response(event)
        decision, timestamp_ms, _ = scenario[expected_cursor]
        if decision == CaptionDecision.WAIT:
            return _wait_response(session.id, expected_cursor, timestamp_ms)
        raise AppError("EVENT_NOT_FOUND", "Stored demo event is missing.", 409)

    if expected_cursor != session.demo_cursor:
        raise AppError("CURSOR_OUT_OF_ORDER", "Expected cursor does not match the session.", 409)
    if session.status != SessionStatus.ACTIVE:
        raise AppError("SESSION_NOT_ACTIVE", "Session is not active.", 409)
    if expected_cursor >= len(scenario):
        raise AppError("SCENARIO_COMPLETED", "Demo scenario has ended.", 409)

    decision, timestamp_ms, text = scenario[expected_cursor]
    claim = db.execute(
        update(SessionModel)
        .where(
            SessionModel.id == session.id,
            SessionModel.demo_cursor == expected_cursor,
            SessionModel.status == SessionStatus.ACTIVE,
        )
        .values(demo_cursor=expected_cursor + 1, last_event_index=expected_cursor)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise AppError(
            "CURSOR_OUT_OF_ORDER", "Session advanced concurrently; retry with the same cursor.", 409
        )

    if decision == CaptionDecision.WAIT:
        db.commit()
        return _wait_response(session.id, expected_cursor, timestamp_ms)

    now = datetime.now(UTC)
    caption_id = demo_caption_id(session.id)
    caption = db.get(CaptionModel, caption_id)
    if decision == CaptionDecision.EMIT:
        if caption is not None:
            db.rollback()
            raise AppError("CAPTION_CONFLICT", "Demo caption already exists.", 409)
        caption = CaptionModel(
            id=caption_id,
            session_id=session.id,
            current_text=text,
            version=1,
            status="VISIBLE",
            created_at=now,
            updated_at=now,
        )
        db.add(caption)
        db.flush()
        version = 1
        previous_id = None
    else:
        if caption is None or caption.session_id != session.id or caption.status != "VISIBLE":
            db.rollback()
            raise AppError("CAPTION_CONFLICT", "Caption is not available for change.", 409)
        previous = db.scalar(
            select(CaptionEventModel)
            .where(
                CaptionEventModel.session_id == session.id,
                CaptionEventModel.caption_id == caption_id,
            )
            .order_by(CaptionEventModel.caption_version.desc())
            .limit(1)
        )
        if previous is None:
            db.rollback()
            raise AppError("CAPTION_CONFLICT", "Previous caption event is missing.", 409)
        version = caption.version + 1
        previous_id = previous.id
        caption.version = version
        caption.current_text = text
        caption.status = "WITHDRAWN" if decision == CaptionDecision.WITHDRAW else "VISIBLE"
        caption.updated_at = now

    event = CaptionEventModel(
        id=demo_event_id(session.id, expected_cursor),
        session_id=session.id,
        caption_id=caption_id,
        event_index=expected_cursor,
        timestamp_ms=timestamp_ms,
        decision=decision.value,
        text=text,
        caption_version=version,
        previous_event_id=previous_id,
        model_version=DEMO_MODEL_VERSION,
        is_demo=True,
        start_ms=timestamp_ms,
        end_ms=timestamp_ms,
        model_id=DEMO_MODEL_VERSION,
        inference_ms=0,
        processing_delay_ms=0,
        is_mock=True,
        created_at=now,
    )
    db.add(event)
    db.commit()
    return event_response(event)


def _wait_response(session_id: str, cursor: int, timestamp_ms: int) -> CaptionEventResponse:
    return CaptionEventResponse(
        event_id=demo_event_id(session_id, cursor),
        session_id=session_id,
        event_index=cursor,
        timestamp_ms=timestamp_ms,
        decision=CaptionDecision.WAIT,
        model_version=DEMO_MODEL_VERSION,
        is_demo=True,
        start_ms=timestamp_ms,
        end_ms=timestamp_ms,
        model_id=DEMO_MODEL_VERSION,
        is_mock=True,
    )
