from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SwapItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
