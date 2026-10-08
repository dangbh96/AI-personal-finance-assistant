from app.ai import openai_client
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_is_configured_false_without_key():
    assert openai_client.is_configured(_settings(openai_api_key=None)) is False
    assert openai_client.is_configured(_settings(openai_api_key="   ")) is False


def test_is_configured_true_with_key():
    assert openai_client.is_configured(_settings(openai_api_key="sk-test")) is True


def test_models_read_from_settings():
    s = _settings(openai_model_fast="fast-x", openai_model_smart="smart-y")
    assert openai_client.model_fast(s) == "fast-x"
    assert openai_client.model_smart(s) == "smart-y"


def test_cors_origins_parsed_from_comma_string(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://127.0.0.1:3000")
    assert _settings().cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_api_key_not_in_repr():
    assert "sk-secret" not in repr(_settings(openai_api_key="sk-secret"))
