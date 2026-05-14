"""
User profile, follow graph, and friend activity feed.

  POST   /api/users/{username}/follow     — follow a user (auth required)
  DELETE /api/users/{username}/follow     — unfollow (auth required)
  GET    /api/users/{username}            — public profile
  GET    /api/users/{username}/followers  — paginated follower list
  GET    /api/users/{username}/following  — paginated following list
  GET    /api/users/search?q=            — username prefix search
  GET    /api/users/feed                 — friend activity feed (auth required)
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models.activity import UserActivity
from app.models.follow import Follow
from app.models.sample import Sample
from app.models.user import User
from app.schemas.follow import ActivityOut, UserProfile, UserPublic

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_by_username(username: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _is_following(
    db: AsyncSession, follower_id: uuid.UUID, following_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        )
    )
    return result.scalar_one_or_none() is not None


# ── Follow / unfollow ─────────────────────────────────────────────────────────

@router.post("/{username}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def follow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await _get_user_by_username(username, db)
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    if await _is_following(db, current_user.id, target.id):
        return  # idempotent — already following
    db.add(Follow(follower_id=current_user.id, following_id=target.id))
    await db.commit()


@router.delete("/{username}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await _get_user_by_username(username, db)
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target.id,
        )
    )
    follow = result.scalar_one_or_none()
    if follow:
        await db.delete(follow)
        await db.commit()
    # Idempotent: 204 even if not following


@router.delete("/{username}/follower", status_code=status.HTTP_204_NO_CONTENT)
async def remove_follower(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a specific user from your followers (they can no longer see you followed them)."""
    target = await _get_user_by_username(username, db)
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == target.id,
            Follow.following_id == current_user.id,
        )
    )
    follow = result.scalar_one_or_none()
    if follow:
        await db.delete(follow)
        await db.commit()
    # Idempotent: 204 even if they weren't following you


# ── Profile ───────────────────────────────────────────────────────────────────

# NOTE: "search" and "feed" must be declared BEFORE "/{username}" so FastAPI
# does not treat the literal path segments as username values.

@router.get("/search", response_model=List[UserPublic])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.username.ilike(f"{q}%"))
        .where(User.is_active == True)  # noqa: E712
        .order_by(User.username)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/feed", response_model=List[ActivityOut])
async def get_feed(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activity feed: actions performed by users the current user follows."""
    following_ids_result = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == current_user.id)
    )
    following_ids = [r.following_id for r in following_ids_result.all()]

    if not following_ids:
        return []

    rows = await db.execute(
        select(
            UserActivity.id,
            UserActivity.user_id,
            User.username,
            UserActivity.activity_type,
            UserActivity.sample_id,
            Sample.title.label("sample_title"),
            UserActivity.activity_data,
            UserActivity.created_at,
        )
        .join(User, UserActivity.user_id == User.id)
        .outerjoin(Sample, UserActivity.sample_id == Sample.id)
        .where(UserActivity.user_id.in_(following_ids))
        .order_by(UserActivity.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        ActivityOut(
            id=r.id,
            user_id=r.user_id,
            username=r.username,
            activity_type=r.activity_type,
            sample_id=r.sample_id,
            sample_title=r.sample_title,
            activity_data=r.activity_data,
            created_at=r.created_at,
        )
        for r in rows.all()
    ]


@router.get("/{username}", response_model=UserProfile)
async def get_user_profile(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    target = await _get_user_by_username(username, db)

    follower_count = (await db.execute(
        select(func.count()).where(Follow.following_id == target.id)
    )).scalar_one()

    following_count = (await db.execute(
        select(func.count()).where(Follow.follower_id == target.id)
    )).scalar_one()

    is_following = (
        await _is_following(db, current_user.id, target.id)
        if current_user and current_user.id != target.id
        else False
    )

    return UserProfile(
        id=target.id,
        username=target.username,
        created_at=target.created_at,
        follower_count=follower_count,
        following_count=following_count,
        is_following=is_following,
    )


@router.get("/{username}/followers", response_model=List[UserPublic])
async def list_followers(
    username: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    target = await _get_user_by_username(username, db)
    rows = await db.execute(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == target.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows.scalars().all()


@router.get("/{username}/following", response_model=List[UserPublic])
async def list_following(
    username: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    target = await _get_user_by_username(username, db)
    rows = await db.execute(
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == target.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows.scalars().all()
