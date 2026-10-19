from fastapi import APIRouter

from app.api.routers import categories, classification_preferences, health, transactions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(classification_preferences.router)
