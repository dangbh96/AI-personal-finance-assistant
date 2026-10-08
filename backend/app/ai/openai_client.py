"""Điểm truy cập duy nhất tới OpenAI.

Phase 0 chỉ có khung: đọc cấu hình từ env. Lời gọi API thật được thêm ở Phase 2.
"""

from app.core.config import Settings, get_settings


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.openai_api_key and settings.openai_api_key.strip())


def model_fast(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_model_fast


def model_smart(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_model_smart


def embedding_model(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_embedding_model
