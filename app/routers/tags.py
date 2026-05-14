"""
  GET /api/tags/  — list tags with sample counts, sorted by frequency
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tag import SampleTag, Tag

router = APIRouter()


class TagWithCount(BaseModel):
    name: str
    category: str
    sample_count: int


@router.get("/", response_model=List[TagWithCount])
async def list_tags(
    category: str = Query(default=None, description="Filter by category: yamnet, musicnn, manual"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return tags with sample counts, sorted by frequency descending."""
    query = (
        select(Tag.name, Tag.category, func.count(SampleTag.sample_id).label("sample_count"))
        .join(SampleTag, Tag.id == SampleTag.tag_id)
        .group_by(Tag.id, Tag.name, Tag.category)
        .order_by(func.count(SampleTag.sample_id).desc())
        .limit(limit)
    )
    if category:
        query = query.where(Tag.category == category)

    rows = await db.execute(query)
    return [
        TagWithCount(name=r.name, category=r.category, sample_count=r.sample_count)
        for r in rows.all()
    ]
