import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.api.v1.routes import get_ai_client
from app.api.v1.streaming import get_ai_stream_client
from app.database.session import Base, get_db
from app.main import app
from app.models.caption import CaptionEventModel
from app.repositories.sessions import SessionRepository
from app.schemas.contracts import (
    ModelInfoResponse,
    SessionCreateRequest,
    SessionMode,
    SessionSource,
)
from app.schemas.streaming import CaptionMessage
from app.services.streaming import persist_caption_event


class FakeAIClient:
    def __init__(self, fail_connect: bool = False) -> None:
        self.fail_connect = fail_connect
        self.calls: list[str] = []

    async def get_model_info(self) -> ModelInfoResponse:
        self.calls.append("model_info")
        if self.fail_connect:
            from app.core.errors import AppError

            raise AppError("AI_SERVICE_UNAVAILABLE", "AI Service is unavailable.", 503)
        return ModelInfoResponse(
            provider="mock",
            provider_type="MOCK",
            model_name="Mock Inference",
            model_version="mock-gru-v1",
            real_model_ready=False,
            supported_modes=[SessionMode.DEMO],
        )

    async def health_check(self) -> bool:
        return not self.fail_connect


class FakeUpstreamSocket:
    def __init__(self) -> None:
        self.frame: dict[str, object] = {}

    async def send(self, payload: str) -> None:
        self.frame = json.loads(payload)

    async def recv(self) -> str:
        return json.dumps(
            {
                "type": "caption",
                "stream_id": self.frame["stream_id"],
                "event_id": "gateway-event-1",
                "start_ms": 400,
                "end_ms": 2300,
                "caption": "A person is picking up a ball.",
                "model_id": "mock-smolvlm2-500m-v1",
                "inference_ms": 3.2,
                "processing_delay_ms": 0,
                "is_mock": True,
            }
        )


class FakeAIStreamClient:
    @asynccontextmanager
    async def connect(self, _stream_id: str):
        yield FakeUpstreamSocket()


@pytest.fixture()
def test_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield testing_session
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def fake_ai(test_db):
    client = FakeAIClient(fail_connect=True)
    app.dependency_overrides[get_ai_client] = lambda: client
    return client


async def async_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def create_demo(ac: AsyncClient) -> str:
    response = await ac.post(
        "/api/v1/sessions",
        json={"source": "DEMO", "mode": "DEMO", "scenario_id": "cup_interaction"},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


async def advance(ac: AsyncClient, session_id: str, cursor: int):
    return await ac.post(f"/api/v1/sessions/{session_id}/advance", json={"expected_cursor": cursor})


@pytest.mark.asyncio
async def test_demo_runs_without_ai_and_replays_requests(fake_ai: FakeAIClient):
    async with await async_client() as ac:
        session_id = await create_demo(ac)
        events = []
        for cursor in range(4):
            response = await advance(ac, session_id, cursor)
            assert response.status_code == 200, response.text
            events.append(response.json())
            replay = await advance(ac, session_id, cursor)
            assert replay.json()["event_id"] == events[-1]["event_id"]

        assert [item["decision"] for item in events] == ["WAIT", "EMIT", "REVISE", "WITHDRAW"]
        assert events[0]["caption_id"] is None
        assert [item["caption_version"] for item in events[1:]] == [1, 2, 3]
        assert events[2]["previous_event_id"] == events[1]["event_id"]
        assert events[3]["previous_event_id"] == events[2]["event_id"]
        assert not fake_ai.calls

        history = await ac.get(f"/api/v1/sessions/{session_id}/caption-events")
        assert history.json()["total"] == 3
        assert [item["decision"] for item in history.json()["items"]] == [
            "EMIT",
            "REVISE",
            "WITHDRAW",
        ]
        captions = await ac.get(f"/api/v1/sessions/{session_id}/captions")
        assert captions.json()["items"][0]["status"] == "WITHDRAWN"
        assert captions.json()["items"][0]["current_text"] is None
        assert (await advance(ac, session_id, 4)).json()["error"]["code"] == "SCENARIO_COMPLETED"


@pytest.mark.asyncio
async def test_demo_cursor_persists_and_rejects_out_of_order(fake_ai: FakeAIClient):
    async with await async_client() as ac:
        session_id = await create_demo(ac)
        assert (await advance(ac, session_id, 2)).status_code == 409
        assert (await advance(ac, session_id, 0)).status_code == 200
        session = await ac.get(f"/api/v1/sessions/{session_id}")
        assert session.json()["demo_cursor"] == 1
        assert (await advance(ac, session_id, 0)).status_code == 200
        assert (await advance(ac, session_id, 1)).status_code == 200
        page = await ac.get(
            f"/api/v1/sessions/{session_id}/caption-events",
            params={"limit": 1, "offset": 0},
        )
        assert page.json()["total"] == 1
        assert len(page.json()["items"]) == 1


@pytest.mark.asyncio
async def test_concurrent_advance_creates_one_caption_event(fake_ai: FakeAIClient):
    async with await async_client() as ac:
        session_id = await create_demo(ac)
        assert (await advance(ac, session_id, 0)).status_code == 200
        responses = await asyncio.gather(
            advance(ac, session_id, 1), advance(ac, session_id, 1)
        )
        assert all(response.status_code in {200, 409} for response in responses)
        assert any(response.status_code == 200 for response in responses)
        retry = await advance(ac, session_id, 1)
        assert retry.status_code == 200
        history = await ac.get(f"/api/v1/sessions/{session_id}/caption-events")
        assert history.json()["total"] == 1


@pytest.mark.asyncio
async def test_pause_resume_stop_and_session_isolation(fake_ai: FakeAIClient):
    async with await async_client() as ac:
        first = await create_demo(ac)
        second = await create_demo(ac)
        assert (await advance(ac, first, 0)).status_code == 200
        assert (await ac.post(f"/api/v1/sessions/{first}/pause")).status_code == 200
        assert (await advance(ac, first, 1)).status_code == 409
        assert (await advance(ac, second, 0)).status_code == 200
        assert (await ac.post(f"/api/v1/sessions/{first}/resume")).status_code == 200
        assert (await advance(ac, first, 1)).status_code == 200
        assert (await ac.delete(f"/api/v1/sessions/{first}")).status_code == 200
        assert (await ac.delete(f"/api/v1/sessions/{first}")).status_code == 200
        assert (await advance(ac, first, 2)).status_code == 409
        assert (await ac.get(f"/api/v1/sessions/{second}/caption-events")).json()["total"] == 0
        assert (await ac.get(f"/api/v1/sessions/{first}/caption-events")).json()["total"] == 1
        assert not fake_ai.calls


@pytest.mark.asyncio
async def test_live_requires_real_model_and_demo_validates_scenario(test_db):
    ai = FakeAIClient()
    app.dependency_overrides[get_ai_client] = lambda: ai
    async with await async_client() as ac:
        live = await ac.post("/api/v1/sessions", json={"source": "CAMERA", "mode": "LIVE"})
        assert live.status_code == 503
        assert live.json()["error"]["code"] == "MODEL_NOT_READY"
        bad_demo = await ac.post(
            "/api/v1/sessions",
            json={"source": "DEMO", "mode": "DEMO", "scenario_id": "unknown"},
        )
        assert bad_demo.status_code == 422
        assert ai.calls == ["model_info"]


@pytest.mark.asyncio
async def test_demo_and_backend_ready_when_ai_offline(fake_ai: FakeAIClient):
    async with await async_client() as ac:
        session_id = await create_demo(ac)
        assert session_id
        ready = await ac.get("/readyz")
        assert ready.json() == {"status": "ready", "backend": "ONLINE", "ai_service": "OFFLINE"}


def test_migration_preserves_existing_sessions(tmp_path, monkeypatch):
    from pathlib import Path

    from app.core.config import get_settings

    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    try:
        command.upgrade(config, "0001_initial_schema")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sessions (id, source, mode, status, model_version, created_at) "
                    "VALUES ('old-session', 'DEMO', 'DEMO', 'COMPLETED', 'old-model', '2026-01-01')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sessions (id, source, mode, status, model_version, created_at) "
                    "VALUES ('open-demo', 'DEMO', 'DEMO', 'ACTIVE', 'old-model', '2026-01-01')"
                )
            )
        command.upgrade(config, "head")
        assert {"captions", "caption_events"}.issubset(inspect(engine).get_table_names())
        event_columns = {column["name"] for column in inspect(engine).get_columns("caption_events")}
        assert {
            "start_ms",
            "end_ms",
            "model_id",
            "inference_ms",
            "processing_delay_ms",
            "is_mock",
        }.issubset(event_columns)
        with engine.connect() as connection:
            old = connection.execute(
                text(
                    "SELECT id, demo_cursor, last_event_index FROM sessions WHERE id = 'old-session'"
                )
            ).one()
            assert tuple(old) == ("old-session", 0, -1)
            open_demo = connection.execute(
                text("SELECT status, ended_at FROM sessions WHERE id = 'open-demo'")
            ).one()
            assert open_demo[0] == "COMPLETED"
            assert open_demo[1] is not None
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_streaming_caption_persistence_is_idempotent(test_db):
    with test_db() as db:
        session = SessionRepository(db).create(
            SessionCreateRequest(source=SessionSource.CAMERA, mode=SessionMode.LIVE),
            "mock-smolvlm2-500m-v1",
        )
        message = CaptionMessage(
            stream_id=session.id,
            event_id="stream-event-1",
            start_ms=400,
            end_ms=2300,
            caption="A person is picking up a ball.",
            model_id="mock-smolvlm2-500m-v1",
            inference_ms=4.5,
            processing_delay_ms=2.0,
            is_mock=True,
        )

        first = persist_caption_event(db, session, 5, message)
        replay = persist_caption_event(db, session, 6, message)
        events = db.query(CaptionEventModel).all()

        assert replay.id == first.id
        assert len(events) == 1
        assert events[0].start_ms == 400
        assert events[0].end_ms == 2300
        assert events[0].model_id == "mock-smolvlm2-500m-v1"
        assert events[0].is_mock is True
        assert session.last_event_index == 0
        assert session.last_frame_index == 6


def test_websocket_gateway_forwards_and_persists_caption(test_db):
    with test_db() as db:
        session = SessionRepository(db).create(
            SessionCreateRequest(source=SessionSource.CAMERA, mode=SessionMode.LIVE),
            "mock-smolvlm2-500m-v1",
        )
        session_id = session.id

    app.dependency_overrides[get_ai_stream_client] = lambda: FakeAIStreamClient()
    try:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/v1/streams/{session_id}") as websocket,
        ):
            websocket.send_json(
                {
                    "type": "frame",
                    "stream_id": session_id,
                    "frame_index": 0,
                    "timestamp_ms": 2300,
                    "image_b64": "mock-image",
                }
            )
            response = websocket.receive_json()
            assert response["type"] == "caption"
            assert response["event_id"] == "gateway-event-1"

        with test_db() as db:
            event = db.get(CaptionEventModel, "gateway-event-1")
            assert event is not None
            assert event.session_id == session_id
            assert event.start_ms == 400
            assert event.end_ms == 2300
    finally:
        app.dependency_overrides.pop(get_ai_stream_client, None)
