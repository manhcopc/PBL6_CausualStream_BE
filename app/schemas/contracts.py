from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SessionSource(StrEnum):
    CAMERA = "CAMERA"
    VIDEO = "VIDEO"
    DEMO = "DEMO"


class SessionMode(StrEnum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Decision(StrEnum):
    WAIT = "WAIT"
    SPEAK = "SPEAK"
    UPDATE = "UPDATE"


class SessionCreateRequest(BaseModel):
    source: SessionSource
    mode: SessionMode
    scenario_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    source: SessionSource
    mode: SessionMode
    status: SessionStatus
    model_version: str
    is_demo: bool
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_frame_index: int | None = None
    demo_cursor: int = 0


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int
    limit: int
    offset: int


class PredictionResponse(BaseModel):
    prediction_id: str
    session_id: str
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    action_id: str
    action_label: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    decision: Decision
    message: str | None = None
    previous_prediction_id: str | None = None
    model_version: str
    inference_time_ms: float | None = None
    is_demo: bool
    created_at: datetime | None = None


class PredictionListResponse(BaseModel):
    items: list[PredictionResponse]
    total: int
    limit: int
    offset: int


class CaptionDecision(StrEnum):
    WAIT = "WAIT"
    EMIT = "EMIT"
    REVISE = "REVISE"
    WITHDRAW = "WITHDRAW"


class AdvanceDemoRequest(BaseModel):
    expected_cursor: int = Field(ge=0)


class CaptionEventResponse(BaseModel):
    event_id: str
    session_id: str
    event_index: int
    timestamp_ms: int
    decision: CaptionDecision
    caption_id: str | None = None
    text: str | None = None
    caption_version: int | None = None
    previous_event_id: str | None = None
    model_version: str
    is_demo: bool
    start_ms: int | None = None
    end_ms: int | None = None
    model_id: str | None = None
    inference_ms: float | None = None
    processing_delay_ms: float | None = None
    is_mock: bool = False
    created_at: datetime | None = None


class CaptionEventListResponse(BaseModel):
    items: list[CaptionEventResponse]
    total: int
    limit: int
    offset: int


class CaptionResponse(BaseModel):
    caption_id: str
    session_id: str
    current_text: str | None
    version: int
    status: str
    created_at: datetime
    updated_at: datetime


class CaptionListResponse(BaseModel):
    items: list[CaptionResponse]


class CompletionResponse(BaseModel):
    completed: bool = True
    session_id: str
    message: str


class ModelInfoResponse(BaseModel):
    provider: str
    provider_type: str
    model_name: str
    model_version: str
    real_model_ready: bool
    supported_modes: list[SessionMode]


class HealthResponse(BaseModel):
    status: str


class BackendReadinessResponse(BaseModel):
    status: str
    backend: str
    ai_service: str


class SystemStatusResponse(BaseModel):
    backend: dict[str, Any]
    ai_service: dict[str, Any]
    active_sessions: int
