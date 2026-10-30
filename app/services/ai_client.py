from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.contracts import ModelInfoResponse, PredictionResponse, SessionMode


class AIServiceClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.ai_service_url.rstrip("/")
        self.timeout = settings.ai_service_timeout_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise AppError("AI_SERVICE_UNAVAILABLE", "AI Service is unavailable.", 503) from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {
                    "error": {"code": "AI_SERVICE_ERROR", "message": response.text, "details": None}
                }
            error = payload.get("error", {})
            raise AppError(
                error.get("code", "AI_SERVICE_ERROR"),
                error.get("message", "AI Service request failed."),
                response.status_code,
                error.get("details"),
            )
        return response.json()

    async def create_session(
        self, session_id: str, mode: SessionMode, scenario_id: str | None
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/v1/sessions",
            json={"session_id": session_id, "mode": mode.value, "scenario_id": scenario_id},
        )

    async def advance_demo(self, session_id: str) -> PredictionResponse:
        payload = await self._request("POST", f"/internal/v1/sessions/{session_id}/advance")
        return PredictionResponse.model_validate(payload)

    async def infer_frame(
        self,
        session_id: str,
        frame: bytes,
        filename: str,
        content_type: str,
        frame_index: int,
        timestamp_ms: int,
    ) -> PredictionResponse:
        payload = await self._request(
            "POST",
            f"/internal/v1/sessions/{session_id}/infer",
            data={"frame_index": str(frame_index), "timestamp_ms": str(timestamp_ms)},
            files={"frame": (filename, frame, content_type)},
        )
        return PredictionResponse.model_validate(payload)

    async def pause_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/internal/v1/sessions/{session_id}/pause")

    async def resume_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/internal/v1/sessions/{session_id}/resume")

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/internal/v1/sessions/{session_id}")

    async def get_model_info(self) -> ModelInfoResponse:
        payload = await self._request("GET", "/internal/v1/models/current")
        return ModelInfoResponse.model_validate(payload)

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/healthz")
        except AppError:
            return False
        return True

    async def system_status(self) -> dict[str, Any]:
        return await self._request("GET", "/internal/v1/system/status")
