from pydantic import BaseModel
from typing import Dict


class SettingsBulk(BaseModel):
    settings: Dict[str, str]
