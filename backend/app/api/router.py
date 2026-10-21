from fastapi import APIRouter

from app.api.routers import (
    budget_allocations,
    budgets,
    categories,
    classification_preferences,
    dashboard,
    health,
    reviews,
    transactions,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(classification_preferences.router)
api_router.include_router(budgets.router)
api_router.include_router(budget_allocations.router)
api_router.include_router(dashboard.router)
api_router.include_router(reviews.router)
