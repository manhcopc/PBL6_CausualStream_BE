from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit, urlunsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from app.core.config import Settings


class AIStreamUnavailable(Exception):
    pass


class AIStreamClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def stream_url(self, stream_id: str) -> str:
        parsed = urlsplit(self.settings.ai_service_url.rstrip("/"))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        base_path = parsed.path.rstrip("/")
        path = f"{base_path}/v1/streams/{quote(stream_id, safe='')}"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))

    @asynccontextmanager
    async def connect(self, stream_id: str) -> AsyncIterator[ClientConnection]:
        try:
            async with connect(
                self.stream_url(stream_id),
                open_timeout=self.settings.ai_service_timeout_seconds,
                close_timeout=2,
                max_size=self.settings.max_frame_size_mb * 1024 * 1024 * 2,
            ) as socket:
                yield socket
        except (OSError, TimeoutError, WebSocketException) as exc:
            raise AIStreamUnavailable("AI streaming service is unavailable.") from exc
