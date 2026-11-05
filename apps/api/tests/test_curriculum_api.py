"""TypeVector Arena — Curriculum API Integration Tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.main import app


@pytest.mark.asyncio
async def test_list_curriculum_tracks() -> None:
    """Verify listing all 7 curriculum tracks via REST API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/curriculum/tracks")
        assert res.status_code == 200
        tracks = res.json()
        assert len(tracks) == 7
        slugs = [t["slug"] for t in tracks]
        assert "keyboard-fundamentals" in slugs
        assert "code-typing" in slugs
        assert "precision-typing" in slugs


@pytest.mark.asyncio
async def test_get_curriculum_track_detail_and_levels() -> None:
    """Verify fetching track details with all 6 versioned levels."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/curriculum/tracks/sentence-fluency")
        assert res.status_code == 200
        track = res.json()
        assert track["slug"] == "sentence-fluency"
        assert len(track["levels"]) == 6
        assert track["levels"][0]["level_number"] == 1
        assert track["levels"][0]["criteria_version"] == "2026.1-draft"


@pytest.mark.asyncio
async def test_get_curriculum_track_not_found_404() -> None:
    """Verify 404 EntityNotFoundError when querying an invalid track."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/curriculum/tracks/non-existent-slug")
        assert res.status_code == 404
        data = res.json()
        assert data["code"] == "ENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_curriculum_progress_unauthorized_when_not_signed_in() -> None:
    """Verify curriculum progress endpoint requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/curriculum/progress")
        assert res.status_code == 401
        assert res.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_curriculum_assessment_unauthorized_when_not_signed_in() -> None:
    """Verify assessment submission requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "track_slug": "keyboard-fundamentals",
            "level_number": 1,
            "input_text": "asdf jkl;",
            "started_at": "2026-11-04T00:00:00Z",
            "completed_at": "2026-11-04T00:00:10Z",
        }
        res = await client.post("/api/v1/curriculum/assessments", json=payload)
        assert res.status_code == 401
        assert res.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_curriculum_recommendations_unauthorized_when_not_signed_in() -> None:
    """Verify adaptive recommendations require authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/curriculum/recommendations")
        assert res.status_code == 401
        assert res.json()["code"] == "UNAUTHORIZED"
