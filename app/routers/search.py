import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_optional_user
from app.models.sample import Sample
from app.models.system import SearchQuery, QueryType
from app.models.user import User
from app.schemas.search import TextSearchRequest, SearchResponse
from app.schemas.sample import SampleOut
from app.workers import registry

router = APIRouter()

# CLAP (~900 MB) exceeds Railway's 512 MB free-tier limit. Search endpoints must
# only run on the local machine (exposed via ngrok). If a request somehow reaches
# Railway (stale VITE_SEARCH_URL, misconfigured frontend), fail fast with 503
# instead of OOMing and crashing the container.
_ON_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT"))


def _require_search_available() -> None:
    if _ON_RAILWAY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Search is not available on the Railway backend. "
                "Configure VITE_SEARCH_URL to point to the local ngrok tunnel."
            ),
        )


def _vec_to_pg(vec: list[float]) -> str:
    """Format a Python float list as a Postgres vector literal."""
    return "[" + ",".join(map(str, vec)) + "]"


async def _vector_search(
    db: AsyncSession, embedding: list[float], limit: int, offset: int
) -> list[Sample]:
    """
    Run cosine similarity search via pgvector, then do a follow-up ORM fetch with
    selectinload so that audio_metadata and tags are populated on each Sample.
    """
    # Step 1: get ordered IDs from the vector index
    id_rows = await db.execute(
        text("""
            SELECT s.id
            FROM samples s
            JOIN audio_embeddings ae ON s.id = ae.sample_id
            ORDER BY ae.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit OFFSET :offset
        """),
        {"embedding": _vec_to_pg(embedding), "limit": limit, "offset": offset},
    )
    ordered_ids = [row[0] for row in id_rows]
    if not ordered_ids:
        return []

    # Step 2: ORM fetch with eager-loaded relationships
    orm_result = await db.execute(
        select(Sample)
        .options(selectinload(Sample.audio_metadata), selectinload(Sample.tags))
        .where(Sample.id.in_(ordered_ids))
    )
    by_id = {s.id: s for s in orm_result.scalars().all()}

    # Restore distance order
    return [by_id[sid] for sid in ordered_ids if sid in by_id]


def _clap_encode_text(text: str) -> list[float]:
    """Run inside a thread executor — initialises CLAP on first call."""
    return registry.clap().encode_text(text)


def _clap_encode_audio(audio_bytes: bytes) -> list[float]:
    """Run inside a thread executor — initialises CLAP on first call."""
    return registry.clap().encode_audio(audio_bytes)


@router.post("/text", response_model=SearchResponse)
async def search_by_text(
    payload: TextSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    _require_search_available()
    loop = asyncio.get_running_loop()
    try:
        query_vector = await loop.run_in_executor(None, _clap_encode_text, payload.query)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search unavailable: {exc}")
    rows = await _vector_search(db, query_vector, payload.limit, payload.offset)

    samples = [SampleOut.model_validate(s) for s in rows]

    db.add(SearchQuery(
        query_text=payload.query,
        query_type=QueryType.text,
        result_count=len(samples),
        user_id=current_user.id if current_user else None,
    ))
    await db.commit()

    return SearchResponse(results=samples, total=len(samples), query=payload.query)


@router.post("/audio", response_model=SearchResponse)
async def search_by_audio(
    file: UploadFile = File(...),
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    _require_search_available()
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an audio file")

    audio_bytes = await file.read()
    loop = asyncio.get_running_loop()
    try:
        query_vector = await loop.run_in_executor(None, _clap_encode_audio, audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search unavailable: {exc}")
    rows = await _vector_search(db, query_vector, limit, 0)

    samples = [SampleOut.model_validate(s) for s in rows]

    db.add(SearchQuery(
        query_type=QueryType.audio,
        result_count=len(samples),
        user_id=current_user.id if current_user else None,
    ))
    await db.commit()

    return SearchResponse(results=samples, total=len(samples))
