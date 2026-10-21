from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting


def get_value(db: Session, key: str) -> Any | None:
    setting = db.get(AppSetting, key)
    return None if setting is None else setting.value


def set_value(db: Session, key: str, value: Any) -> None:
    """Tạo hoặc ghi đè giá trị (flush, chưa commit)."""
    setting = db.get(AppSetting, key)
    if setting is None:
        db.add(AppSetting(key=key, value=value))
    else:
        setting.value = value
    db.flush()
