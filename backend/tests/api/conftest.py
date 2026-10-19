import pytest

from app.ai import openai_client
from app.ai.openai_client import ChatResult


@pytest.fixture
def categories(client) -> dict[str, dict]:
    """Danh mục seed (theo slug)."""
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    return {c["slug"]: c for c in resp.json()}


@pytest.fixture
def fake_ai(monkeypatch):
    """OpenAI giả: trả lần lượt các chuỗi JSON trong `responses`, ghi lại messages đã gửi."""
    calls: list[dict] = []
    responses: list[str] = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return ChatResult(
            content=responses.pop(0),
            refusal=None,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=50,
        )

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_chat_json", _fake)
    return calls, responses
