"""Smoke tests — verify the app loads and core endpoints respond."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_loads() -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    # Core campaign routes should be registered.
    assert "/api/campaigns" in paths
    assert "/api/campaigns/{campaign_id}" in paths
