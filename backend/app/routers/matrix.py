from fastapi import APIRouter, Depends

from ..auth import CurrentUser, require_user
from ..penalties import MATRIX_DATA, PENALTY_MAP

router = APIRouter(prefix="/matrix", tags=["matrix"])


@router.get("")
def get_matrix(_: CurrentUser = Depends(require_user)):
    return {"matrix": MATRIX_DATA, "penalties": PENALTY_MAP}
