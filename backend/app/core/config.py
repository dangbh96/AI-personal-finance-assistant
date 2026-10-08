from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

APP_VERSION = "0.0.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://pfa:pfa@localhost:5433/pfa"
    test_database_url: str = "postgresql+psycopg://pfa:pfa@localhost:5433/pfa_test"

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_smart: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    upload_dir: Path = Path("./uploads")
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
