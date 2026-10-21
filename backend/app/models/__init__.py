from app.core.db import Base

# Import mọi module ORM ở đây để Alembic autogenerate thấy metadata.
from app.models.app_setting import AppSetting
from app.models.budget import Budget, BudgetAllocation
from app.models.category import Category
from app.models.classification import ClassificationFeedback, ClassificationPreference
from app.models.review import MonthlyReview, ReflectionAnswer, WeeklyReview
from app.models.transaction import Transaction

__all__ = [
    "MonthlyReview",
    "ReflectionAnswer",
    "WeeklyReview",
    "AppSetting",
    "Base",
    "Budget",
    "BudgetAllocation",
    "Category",
    "ClassificationFeedback",
    "ClassificationPreference",
    "Transaction",
]
