from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SystemSetting

APP_DISPLAY_NAME_KEY = "app_display_name"


def get_app_display_name(db: Session) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == APP_DISPLAY_NAME_KEY).first()
    if row and row.value:
        name = str(row.value).strip()
        if name:
            return name
    return get_settings().app_name


def save_app_display_name(db: Session, name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        cleaned = get_settings().app_name
    row = db.query(SystemSetting).filter(SystemSetting.key == APP_DISPLAY_NAME_KEY).first()
    if row:
        row.value = cleaned
    else:
        row = SystemSetting(key=APP_DISPLAY_NAME_KEY, value=cleaned)
        db.add(row)
    db.commit()
    return cleaned
