from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...db.session import get_db
from ...crud.setting import get_all_settings, upsert_settings
from ...schemas.setting import SettingsBulk
from ...api.deps import get_current_user

router = APIRouter()


@router.get("/")
def get_settings(db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    return get_all_settings(db)


@router.put("/")
def update_settings(
    body: SettingsBulk,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    upsert_settings(db, body.settings)
    return {"message": "Settings saved"}
