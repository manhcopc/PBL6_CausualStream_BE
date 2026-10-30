import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator


class FrameMessage(BaseModel):
    type: Literal["frame"] = "frame"
    stream_id: str = Field(min_length=1, max_length=128)
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    image_b64: str = Field(min_length=1)


class CaptionMessage(BaseModel):
    type: Literal["caption"] = "caption"
    stream_id: str
    event_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    caption: str = Field(min_length=1)
    model_id: str
    inference_ms: float | None = Field(default=None, ge=0)
    processing_delay_ms: float | None = Field(default=None, ge=0)
    is_mock: bool = False

    @model_validator(mode="after")
    def validate_interval(self) -> "CaptionMessage":
        if self.start_ms > self.end_ms:
            raise ValueError("start_ms must be less than or equal to end_ms")
        return self


class NoEventMessage(BaseModel):
    type: Literal["no_event"] = "no_event"
    stream_id: str
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)


class StreamErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, object] | None = None


StreamResponse = Annotated[
    CaptionMessage | NoEventMessage | StreamErrorMessage,
    Field(discriminator="type"),
]
stream_response_adapter = TypeAdapter(StreamResponse)


def parse_stream_response(payload: str | bytes) -> StreamResponse:
    return stream_response_adapter.validate_python(json.loads(payload))
