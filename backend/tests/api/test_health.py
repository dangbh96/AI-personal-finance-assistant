import pytest

from app.ai import openai_client
from app.core.config import get_settings


def test_health_ok_when_db_up(client):
    resp = client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"] == "0.0.1"
    assert isinstance(body["ai_configured"], bool)


def test_health_503_when_db_down(client_db_down):
    resp = client_db_down.get("/api/v1/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"


@pytest.mark.parametrize(("key", "expected"), [("", False), ("sk-test", True)])
def test_health_reports_ai_configured(client, monkeypatch, key, expected):
    monkeypatch.setattr(get_settings(), "openai_api_key", key)

    resp = client.get("/api/v1/health")

    assert resp.json()["ai_configured"] is expected
    assert openai_client.is_configured() is expected


def test_openapi_lists_health(client):
    resp = client.get("/openapi.json")

    assert resp.status_code == 200
    assert "/api/v1/health" in resp.json()["paths"]
