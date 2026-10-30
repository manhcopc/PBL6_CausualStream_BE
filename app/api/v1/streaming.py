from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.repositories.sessions import SessionRepository
from app.schemas.contracts import SessionMode, SessionStatus
from app.schemas.streaming import (
    CaptionMessage,
    FrameMessage,
    NoEventMessage,
    StreamErrorMessage,
    parse_stream_response,
)
from app.services.ai_stream import AIStreamClient, AIStreamUnavailable
from app.services.streaming import persist_caption_event, record_processed_frame

router = APIRouter()


def get_ai_stream_client(settings: Settings = Depends(get_settings)) -> AIStreamClient:
    return AIStreamClient(settings)


async def send_error(
    websocket: WebSocket,
    code: str,
    message: str,
    close_code: int,
    details: dict[str, object] | None = None,
) -> None:
    await websocket.send_json(
        StreamErrorMessage(code=code, message=message, details=details).model_dump(mode="json")
    )
    await websocket.close(code=close_code)


@router.websocket("/api/v1/streams/{session_id}")
async def stream_frames(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db),
    ai: AIStreamClient = Depends(get_ai_stream_client),
) -> None:
    await websocket.accept()
    session = SessionRepository(db).get(session_id)
    if session is None:
        await send_error(websocket, "SESSION_NOT_FOUND", "Session was not found.", 4404)
        return
    if session.mode != SessionMode.LIVE:
        await send_error(
            websocket,
            "INVALID_SESSION_MODE",
            "Only LIVE sessions can stream frames.",
            4409,
        )
        return
    if session.status != SessionStatus.ACTIVE:
        await send_error(websocket, "SESSION_NOT_ACTIVE", "Session is not active.", 4409)
        return

    try:
        async with ai.connect(session_id) as upstream:
            while True:
                payload = await websocket.receive_json()
                frame = FrameMessage.model_validate(payload)
                if frame.stream_id != session_id:
                    await send_error(
                        websocket,
                        "STREAM_ID_MISMATCH",
                        "Message stream_id does not match the WebSocket stream.",
                        4409,
                    )
                    return
                if (
                    session.last_frame_index is not None
                    and frame.frame_index <= session.last_frame_index
                ):
                    await send_error(
                        websocket,
                        "FRAME_OUT_OF_ORDER",
                        "Frame index must increase within a stream.",
                        4409,
                    )
                    return

                await upstream.send(frame.model_dump_json())
                response = parse_stream_response(await upstream.recv())
                if isinstance(response, StreamErrorMessage):
                    await websocket.send_json(response.model_dump(mode="json"))
                    await websocket.close(code=4503)
                    return
                if response.stream_id != session_id:
                    await send_error(
                        websocket,
                        "AI_STREAM_MISMATCH",
                        "AI response belongs to another stream.",
                        4502,
                    )
                    return
                if isinstance(response, CaptionMessage):
                    if response.end_ms > frame.timestamp_ms:
                        await send_error(
                            websocket,
                            "CAUSALITY_VIOLATION",
                            "AI emitted an event that ends after the current frame.",
                            4502,
                        )
                        return
                    persist_caption_event(db, session, frame.frame_index, response)
                elif isinstance(response, NoEventMessage):
                    record_processed_frame(db, session, frame.frame_index)
                await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    except ValidationError as exc:
        await send_error(
            websocket,
            "INVALID_MESSAGE",
            "Streaming message does not match contract v1.",
            4400,
            {"errors": exc.errors(include_url=False)},
        )
    except (AIStreamUnavailable, ConnectionClosed):
        await send_error(
            websocket,
            "AI_SERVICE_UNAVAILABLE",
            "AI streaming service is unavailable.",
            4503,
        )
