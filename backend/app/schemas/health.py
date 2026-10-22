from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    vector: Literal["ok", "missing", "error"] = Field(
        default="error", description="Extension pgvector đã bật (Phase 15–16 cần)"
    )
    ai_configured: bool
    version: str
