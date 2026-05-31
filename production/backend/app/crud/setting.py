from sqlalchemy.orm import Session
from typing import Dict
from ..models.setting import AppSetting


def get_all_settings(db: Session) -> Dict[str, str]:
    return {r.key: r.value for r in db.query(AppSetting).all()}


def upsert_settings(db: Session, data: Dict[str, str]) -> None:
    existing = {r.key: r for r in db.query(AppSetting).all()}
    for key, value in data.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.commit()
