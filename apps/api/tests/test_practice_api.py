"""TypeVector Arena — Practice API Integration Tests."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.main import app


@pytest.mark.asyncio
async def test_list_practice_modes() -> None:
    """Verify supported practice modes are returned with expected metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/practice/modes")
        assert res.status_code == 200
        modes = res.json()
        assert len(modes) >= 8
        mode_names = [m["mode"] for m in modes]
        assert "common_words" in mode_names
        assert "sentences" in mode_names
        assert "paragraphs" in mode_names
        assert "precision" in mode_names
        assert "code" in mode_names
        assert "speed_sprint" in mode_names
        assert "accuracy_challenge" in mode_names
        assert "endurance" in mode_names
        assert "diagnostic" in mode_names


@pytest.mark.asyncio
async def test_list_and_filter_practice_prompts() -> None:
    """Verify prompt listing and mode filtering."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # All prompts
        res = await client.get("/api/v1/practice/prompts")
        assert res.status_code == 200
        all_prompts = res.json()
        assert len(all_prompts) >= 9

        # Filter by mode=code
        res_code = await client.get("/api/v1/practice/prompts?mode=code")
        assert res_code.status_code == 200
        code_prompts = res_code.json()
        assert len(code_prompts) >= 1
        assert all(p["mode"] == "code" for p in code_prompts)

        # Single prompt lookup
        first_id = all_prompts[0]["id"]
        res_single = await client.get(f"/api/v1/practice/prompts/{first_id}")
        assert res_single.status_code == 200
        assert res_single.json()["id"] == first_id


@pytest.mark.asyncio
async def test_practice_prompt_not_found_404() -> None:
    """Verify 404 problem details when prompt ID does not exist."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/practice/prompts/unknown-prompt-id")
        assert res.status_code == 404
        data = res.json()
        assert data["code"] == "ENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_practice_history_unauthorized_when_not_logged_in() -> None:
    """Verify practice history requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/practice/history")
        assert res.status_code == 401
        data = res.json()
        assert data["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_submit_anonymous_practice_session(require_postgres: None) -> None:
    """Verify anonymous attempt evaluation and persistence to database."""
    started = datetime.now(UTC) - timedelta(seconds=20)
    completed = datetime.now(UTC)

    payload = {
        "prompt_id": "prompt-cw-01",
        "mode": "common_words",
        "language": "en",
        "target_text": "about their would there which",
        "input_text": "about their would there which",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/practice/sessions", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["is_saved"] is True
        assert data["user_id"] is None
        assert data["metrics"]["accuracy_pct"] == 100.0
        assert data["metrics"]["completion_pct"] == 100.0
        assert len(data["segments"]) == len(payload["target_text"])

        # Fetch saved session
        session_id = data["session_id"]
        res_get = await client.get(f"/api/v1/practice/sessions/{session_id}")
        assert res_get.status_code == 200
        get_data = res_get.json()
        assert get_data["session_id"] == session_id
        assert get_data["metrics"]["accuracy_pct"] == 100.0
