from app.core.db import Base

# Import mọi module ORM ở đây để Alembic autogenerate thấy metadata.
from app.models.app_setting import AppSetting
from app.models.budget import Budget, BudgetAllocation
from app.models.budget_advice import BudgetAdvice
from app.models.category import Category
from app.models.chat import ChatMessage, ChatSession
from app.models.classification import ClassificationFeedback, ClassificationPreference
from app.models.goal import Goal, GoalContribution
from app.models.import_batch import ImportBatch, ImportMappingProfile
from app.models.receipt import Receipt
from app.models.recurring import RecurringTransaction
from app.models.review import MonthlyReview, ReflectionAnswer, WeeklyReview
from app.models.transaction import Transaction

__all__ = [
    "MonthlyReview",
    "ReflectionAnswer",
    "WeeklyReview",
    "AppSetting",
    "Base",
    "Budget",
    "BudgetAdvice",
    "BudgetAllocation",
    "Category",
    "ChatMessage",
    "ChatSession",
    "ClassificationFeedback",
    "ClassificationPreference",
    "Goal",
    "GoalContribution",
    "ImportBatch",
    "ImportMappingProfile",
    "Receipt",
    "RecurringTransaction",
    "Transaction",
]
