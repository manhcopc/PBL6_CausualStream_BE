from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.database.session import get_db
from app.models.caption import CaptionEventModel, CaptionModel
from app.models.prediction import PredictionModel
from app.models.session import SessionModel
from app.repositories.predictions import PredictionRepository
from app.repositories.sessions import SessionRepository
from app.schemas.contracts import (
    AdvanceDemoRequest,
    BackendReadinessResponse,
    CaptionEventListResponse,
    CaptionEventResponse,
    CaptionListResponse,
    CaptionResponse,
    CompletionResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictionListResponse,
    PredictionResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionMode,
    SessionResponse,
    SessionStatus,
    SystemStatusResponse,
)
from app.services.ai_client import AIServiceClient
from app.services.demo import DEMO_MODEL_VERSION, DEMO_SCENARIOS, event_response
from app.services.demo import advance_demo as advance_local_demo
from app.services.validation import validate_session_request, validate_upload

router = APIRouter()


def get_ai_client(settings: Settings = Depends(get_settings)) -> AIServiceClient:
    return AIServiceClient(settings)


def session_to_response(session: SessionModel) -> SessionResponse:
    return SessionResponse(
        session_id=session.id,
        source=session.source,
        mode=session.mode,
        status=session.status,
        model_version=session.model_version,
        is_demo=session.mode == SessionMode.DEMO,
        created_at=session.created_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        last_frame_index=session.last_frame_index,
        demo_cursor=session.demo_cursor,
    )


def prediction_to_response(prediction: PredictionModel) -> PredictionResponse:
    return PredictionResponse(
        prediction_id=prediction.id,
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
        created_at=prediction.created_at,
    )


@router.post("/api/v1/sessions", response_model=SessionResponse)
async def create_session(
    payload: SessionCreateRequest,
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> SessionResponse:
    if payload.mode == SessionMode.DEMO:
        validate_session_request(payload, False)
        if payload.scenario_id not in DEMO_SCENARIOS:
            raise AppError("INVALID_SCENARIO", "Demo scenario is not available.", 422)
        return session_to_response(SessionRepository(db).create(payload, DEMO_MODEL_VERSION))

    model_info = await ai.get_model_info()
    validate_session_request(payload, SessionMode.LIVE in model_info.supported_modes)
    repo = SessionRepository(db)
    session = repo.create(payload, model_info.model_version)
    try:
        await ai.create_session(session.id, payload.mode, payload.scenario_id)
    except AppError:
        repo.update_status(session, SessionStatus.FAILED)
        raise
    return session_to_response(session)


@router.get("/api/v1/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: SessionStatus | None = None,
    mode: SessionMode | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    items, total = SessionRepository(db).list(status, mode, limit, offset)
    return SessionListResponse(
        items=[session_to_response(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionResponse:
    session = SessionRepository(db).get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    return session_to_response(session)


@router.post("/api/v1/sessions/{session_id}/advance", response_model=CaptionEventResponse)
async def advance_demo(
    session_id: str,
    payload: AdvanceDemoRequest,
    db: Session = Depends(get_db),
) -> CaptionEventResponse:
    session_repo = SessionRepository(db)
    session = session_repo.get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    return advance_local_demo(db, session, payload.expected_cursor)


@router.post("/api/v1/sessions/{session_id}/frames", response_model=PredictionResponse)
async def infer_frame(
    session_id: str,
    frame_index: int = Form(..., ge=0),
    timestamp_ms: int = Form(..., ge=0),
    frame: UploadFile = File(...),
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
    settings: Settings = Depends(get_settings),
) -> PredictionResponse:
    session_repo = SessionRepository(db)
    session = session_repo.get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    if session.status != SessionStatus.ACTIVE:
        raise AppError("SESSION_NOT_ACTIVE", "Session is not active.", 409)
    if session.mode != SessionMode.LIVE:
        raise AppError("INVALID_SESSION_MODE", "Only LIVE sessions accept frames.", 409)
    payload = await frame.read()
    validate_upload(frame.content_type, len(payload), settings.max_frame_size_mb)
    if session.last_frame_index is not None and frame_index <= session.last_frame_index:
        raise AppError("FRAME_OUT_OF_ORDER", "Frame index must increase.", 409)
    prediction = await ai.infer_frame(
        session_id,
        payload,
        frame.filename or "frame",
        frame.content_type or "application/octet-stream",
        frame_index,
        timestamp_ms,
    )
    record = PredictionRepository(db).create_from_response(prediction)
    session_repo.update_last_frame(session, prediction.frame_index)
    return prediction_to_response(record)


@router.post("/api/v1/sessions/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: str,
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> SessionResponse:
    repo = SessionRepository(db)
    session = repo.get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    if session.status != SessionStatus.ACTIVE:
        raise AppError("INVALID_STATE_TRANSITION", "Only ACTIVE sessions can be paused.", 409)
    if session.mode != SessionMode.DEMO:
        await ai.pause_session(session_id)
    return session_to_response(repo.update_status(session, SessionStatus.PAUSED))


@router.post("/api/v1/sessions/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: str,
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> SessionResponse:
    repo = SessionRepository(db)
    session = repo.get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    if session.status != SessionStatus.PAUSED:
        raise AppError("INVALID_STATE_TRANSITION", "Only PAUSED sessions can be resumed.", 409)
    if session.mode != SessionMode.DEMO:
        await ai.resume_session(session_id)
    return session_to_response(repo.update_status(session, SessionStatus.ACTIVE))


@router.delete("/api/v1/sessions/{session_id}", response_model=CompletionResponse)
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> CompletionResponse:
    repo = SessionRepository(db)
    session = repo.get(session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    if session.status != SessionStatus.COMPLETED:
        if session.mode != SessionMode.DEMO:
            await ai.delete_session(session_id)
        repo.update_status(session, SessionStatus.COMPLETED)
    return CompletionResponse(session_id=session_id, message="Session completed.")


@router.get("/api/v1/sessions/{session_id}/predictions", response_model=PredictionListResponse)
async def list_predictions(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PredictionListResponse:
    if SessionRepository(db).get(session_id) is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    items, total = PredictionRepository(db).list_for_session(session_id, limit, offset)
    return PredictionListResponse(
        items=[prediction_to_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/v1/sessions/{session_id}/caption-events", response_model=CaptionEventListResponse)
async def list_caption_events(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CaptionEventListResponse:
    if SessionRepository(db).get(session_id) is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    query = select(CaptionEventModel).where(CaptionEventModel.session_id == session_id)
    total = (
        db.scalar(
            select(func.count())
            .select_from(CaptionEventModel)
            .where(CaptionEventModel.session_id == session_id)
        )
        or 0
    )
    events = db.scalars(
        query.order_by(CaptionEventModel.event_index).limit(limit).offset(offset)
    ).all()
    return CaptionEventListResponse(
        items=[event_response(item) for item in events], total=total, limit=limit, offset=offset
    )


@router.get("/api/v1/sessions/{session_id}/captions", response_model=CaptionListResponse)
async def list_captions(session_id: str, db: Session = Depends(get_db)) -> CaptionListResponse:
    if SessionRepository(db).get(session_id) is None:
        raise AppError("SESSION_NOT_FOUND", "Session was not found.", 404)
    items = db.scalars(
        select(CaptionModel)
        .where(CaptionModel.session_id == session_id)
        .order_by(CaptionModel.created_at, CaptionModel.id)
    ).all()
    return CaptionListResponse(
        items=[
            CaptionResponse(
                caption_id=item.id,
                session_id=item.session_id,
                current_text=item.current_text,
                version=item.version,
                status=item.status,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


@router.get("/api/v1/models/current", response_model=ModelInfoResponse)
async def current_model(ai: AIServiceClient = Depends(get_ai_client)) -> ModelInfoResponse:
    return await ai.get_model_info()


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
async def system_status(
    db: Session = Depends(get_db),
    ai: AIServiceClient = Depends(get_ai_client),
) -> SystemStatusResponse:
    ai_online = await ai.health_check()
    ai_status = await ai.system_status() if ai_online else {"status": "OFFLINE"}
    active_sessions = SessionRepository(db).list(SessionStatus.ACTIVE, None, 1, 0)[1]
    return SystemStatusResponse(
        backend={"status": "ONLINE"},
        ai_service=ai_status,
        active_sessions=active_sessions,
    )


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=BackendReadinessResponse)
async def readyz(
    db: Session = Depends(get_db), ai: AIServiceClient = Depends(get_ai_client)
) -> BackendReadinessResponse:
    db.execute(select(1))
    ai_online = await ai.health_check()
    return BackendReadinessResponse(
        status="ready",
        backend="ONLINE",
        ai_service="ONLINE" if ai_online else "OFFLINE",
    )
