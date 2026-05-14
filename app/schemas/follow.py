import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class UserPublic(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowOut(BaseModel):
    follower_id: uuid.UUID
    following_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfile(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime
    follower_count: int
    following_count: int
    is_following: bool   # whether the requesting user follows this profile


class ActivityOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    activity_type: str
    sample_id: Optional[uuid.UUID]
    sample_title: Optional[str]
    activity_data: Optional[dict]
    created_at: datetime
