import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_SERVICES") != "1",
    reason="Requires running Backend on :8000.",
)


@pytest.mark.asyncio
async def test_running_services_demo_flow():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as client:
        created = await client.post(
            "/api/v1/sessions",
            json={"source": "DEMO", "mode": "DEMO", "scenario_id": "cup_interaction"},
        )
        created.raise_for_status()
        session_id = created.json()["session_id"]

        decisions = []
        for cursor in range(4):
            response = await client.post(
                f"/api/v1/sessions/{session_id}/advance", json={"expected_cursor": cursor}
            )
            response.raise_for_status()
            decisions.append(response.json()["decision"])

        history = await client.get(f"/api/v1/sessions/{session_id}/caption-events")
        history.raise_for_status()

        ended = await client.delete(f"/api/v1/sessions/{session_id}")
        ended.raise_for_status()

        assert decisions == ["WAIT", "EMIT", "REVISE", "WITHDRAW"]
        assert history.json()["total"] == 3
