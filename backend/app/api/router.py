from fastapi import APIRouter

from app.api.routers import (
    budget_advice,
    budget_allocations,
    budgets,
    categories,
    classification_preferences,
    coach,
    dashboard,
    forecast,
    goals,
    health,
    imports,
    monthly_reviews,
    receipts,
    recurring_transactions,
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
api_router.include_router(budget_advice.router)
api_router.include_router(dashboard.router)
api_router.include_router(reviews.router)
api_router.include_router(monthly_reviews.router)
api_router.include_router(coach.router)
api_router.include_router(goals.router)
api_router.include_router(recurring_transactions.router)
api_router.include_router(forecast.router)
api_router.include_router(receipts.router)
api_router.include_router(imports.router)
