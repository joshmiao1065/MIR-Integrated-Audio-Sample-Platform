import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    visibility: Literal["public", "friends", "private"] = "public"


class CollectionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    visibility: str
    created_at: datetime

    model_config = {"from_attributes": True}
