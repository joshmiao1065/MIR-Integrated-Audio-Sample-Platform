"""
  GET /api/recommendations/                   — personalized (auth required)
  GET /api/recommendations/similar/{sample_id} — similar samples (public)
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.sample import Sample
from app.schemas.sample import SampleOut
from app.services import rankings, recommendations as rec_service

router = APIRouter()


async def _load_samples_by_ids(
    db: AsyncSession, ids: List[uuid.UUID]
) -> List[Sample]:
    """ORM fetch with eager-loaded relationships, preserving input order."""
    if not ids:
        return []
    result = await db.execute(
        select(Sample)
        .options(selectinload(Sample.audio_metadata), selectinload(Sample.tags))
        .where(Sample.id.in_(ids))
    )
    by_id = {s.id: s for s in result.scalars().all()}
    return [by_id[sid] for sid in ids if sid in by_id]


@router.get("/similar/{sample_id}", response_model=List[SampleOut])
async def similar_samples(
    sample_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Tag-overlap nearest-neighbours for a given sample (no auth required)."""
    ids = await rec_service.get_similar_sample_ids(db, sample_id)
    samples = await _load_samples_by_ids(db, ids)
    return [SampleOut.model_validate(s) for s in samples]


@router.get("/", response_model=List[SampleOut])
async def personalized_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Personalized tag-based recommendations for the authenticated user.
    Falls back to weekly trending when there is no engagement history.
    """
    results = await rec_service.get_recommendations(db, current_user.id)

    if results:
        ids = [r[0] for r in results]
    else:
        # Cold start: fall back to weekly trending
        ids = await rankings.get_cached_rankings(db, "weekly_trending", limit=20)

    samples = await _load_samples_by_ids(db, ids)
    return [SampleOut.model_validate(s) for s in samples]
