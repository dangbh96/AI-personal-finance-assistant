import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.ai import openai_client
from app.core.config import APP_VERSION
from app.core.db import DbSession
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database không kết nối được"}},
)
def health(db: DbSession) -> HealthResponse | JSONResponse:
    """Backend sống + DB kết nối được + pgvector đã bật + đã cấu hình OpenAI (không gọi AI)."""
    ai_configured = openai_client.is_configured()
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
    except SQLAlchemyError as exc:
        logger.warning("Health check: database unavailable (%s)", exc.__class__.__name__)
        body = HealthResponse(
            status="degraded",
            db="error",
            vector="error",
            ai_configured=ai_configured,
            version=APP_VERSION,
        )
        return JSONResponse(status_code=503, content=body.model_dump())
    return HealthResponse(
        status="ok",
        db="ok",
        vector="ok" if has_vector else "missing",
        ai_configured=ai_configured,
        version=APP_VERSION,
    )
