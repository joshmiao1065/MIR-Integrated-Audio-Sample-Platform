"""Lazy TTL-based trending/top-rated ranking cache.

Reads from trending_cache.  If the most recent entry for a window_type is older
than the TTL (7 days for weekly_trending, 1 day for daily_top_rated), the
computation query runs inline, overwrites the cache, and then returns fresh results.

A per-window asyncio.Lock prevents concurrent requests from simultaneously
triggering the same recomputation when the cache goes stale.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ranking import TrendingCache

WindowType = Literal["weekly_trending", "daily_top_rated"]

_TTLS: dict[str, timedelta] = {
    "weekly_trending": timedelta(days=7),
    "daily_top_rated": timedelta(days=1),
}

_LOCKS: dict[str, asyncio.Lock] = {
    "weekly_trending": asyncio.Lock(),
    "daily_top_rated": asyncio.Lock(),
}

_SQL: dict[str, str] = {
    "weekly_trending": """
        SELECT s.id,
          (
            COUNT(DISTINCT dh.id)
            + COALESCE(AVG(r.score) * COUNT(DISTINCT r.id) * 0.5, 0)
          ) AS score
        FROM samples s
        LEFT JOIN download_history dh
          ON dh.sample_id = s.id
          AND dh.downloaded_at > NOW() - INTERVAL '7 days'
        LEFT JOIN ratings r
          ON r.sample_id = s.id
          AND r.created_at > NOW() - INTERVAL '7 days'
        GROUP BY s.id
        HAVING COUNT(DISTINCT dh.id) + COUNT(DISTINCT r.id) > 0
        ORDER BY score DESC
        LIMIT 50
    """,
    "daily_top_rated": """
        SELECT s.id,
          AVG(r.score) AS score
        FROM samples s
        JOIN ratings r ON r.sample_id = s.id
        GROUP BY s.id
        HAVING COUNT(r.id) >= 3
        ORDER BY score DESC, COUNT(r.id) DESC
        LIMIT 50
    """,
}


async def get_cached_rankings(
    db: AsyncSession,
    window_type: WindowType,
    limit: int = 12,
) -> List[uuid.UUID]:
    """Return ordered sample_ids from cache, recomputing inline if stale."""
    ttl = _TTLS[window_type]

    # Fast path: check cache freshness without acquiring the lock
    head = await db.execute(
        select(TrendingCache.computed_at)
        .where(TrendingCache.window_type == window_type)
        .order_by(TrendingCache.rank)
        .limit(1)
    )
    head_row = head.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    is_stale = (
        head_row is None
        or now - head_row.replace(tzinfo=timezone.utc) > ttl
    )

    if is_stale:
        async with _LOCKS[window_type]:
            # Re-check inside lock — another coroutine may have just recomputed
            head2 = await db.execute(
                select(TrendingCache.computed_at)
                .where(TrendingCache.window_type == window_type)
                .order_by(TrendingCache.rank)
                .limit(1)
            )
            head2_row = head2.scalar_one_or_none()
            still_stale = (
                head2_row is None
                or now - head2_row.replace(tzinfo=timezone.utc) > ttl
            )
            if still_stale:
                await _recompute(db, window_type, now)

    rows = await db.execute(
        select(TrendingCache.sample_id)
        .where(TrendingCache.window_type == window_type)
        .order_by(TrendingCache.rank)
        .limit(limit)
    )
    return [r.sample_id for r in rows.all()]


async def _recompute(db: AsyncSession, window_type: str, now: datetime) -> None:
    rows = await db.execute(text(_SQL[window_type]))
    data = rows.all()

    await db.execute(
        delete(TrendingCache).where(TrendingCache.window_type == window_type)
    )
    for rank, row in enumerate(data, start=1):
        db.add(TrendingCache(
            window_type=window_type,
            rank=rank,
            sample_id=row[0],
            score=float(row[1]),
            computed_at=now,
        ))
    await db.commit()
