from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting


def get_value(db: Session, key: str) -> Any | None:
    setting = db.get(AppSetting, key)
    return None if setting is None else setting.value
