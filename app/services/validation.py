from app.core.errors import AppError
from app.schemas.contracts import SessionCreateRequest, SessionMode, SessionSource

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_session_request(payload: SessionCreateRequest, live_mode_ready: bool) -> None:
    if payload.mode == SessionMode.DEMO:
        if payload.source != SessionSource.DEMO:
            raise AppError("INVALID_SESSION_MODE", "DEMO mode requires DEMO source.", 422)
        if not payload.scenario_id:
            raise AppError("INVALID_SCENARIO", "DEMO sessions require scenario_id.", 422)
    if payload.mode == SessionMode.LIVE:
        if payload.source not in {SessionSource.CAMERA, SessionSource.VIDEO}:
            raise AppError(
                "INVALID_SESSION_MODE", "LIVE mode requires CAMERA or VIDEO source.", 422
            )
        if payload.scenario_id is not None:
            raise AppError("INVALID_SESSION_MODE", "LIVE sessions do not accept scenario_id.", 422)
        if not live_mode_ready:
            raise AppError("MODEL_NOT_READY", "The current model does not support LIVE mode.", 503)


def validate_upload(content_type: str | None, size: int, max_size_mb: int) -> None:
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise AppError("INVALID_FRAME", "Unsupported image content type.", 422)
    if size > max_size_mb * 1024 * 1024:
        raise AppError("FRAME_TOO_LARGE", "Frame payload exceeds the configured size limit.", 413)
