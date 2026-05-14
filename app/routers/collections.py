import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models.activity import UserActivity
from app.models.collection import Collection, CollectionItem
from app.models.follow import Follow
from app.models.sample import Sample
from app.models.user import User
from app.schemas.collection import CollectionCreate, CollectionOut
from app.schemas.sample import SampleOut

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _own_collection(
    collection_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your collection")
    return collection


async def _check_visibility(
    collection: Collection,
    current_user: Optional[User],
    db: AsyncSession,
) -> None:
    """Raise 403 if the requesting user cannot view this collection."""
    if collection.visibility == "public":
        return

    if collection.visibility == "private":
        if not current_user or collection.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="This collection is private")
        return

    # friends: mutual follow required (viewer follows owner AND owner follows viewer)
    if collection.visibility == "friends":
        if not current_user:
            raise HTTPException(status_code=403, detail="Log in to view this collection")
        if current_user.id == collection.user_id:
            return  # owner can always see their own

        viewer_follows = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == collection.user_id,
            )
        )
        owner_follows = await db.execute(
            select(Follow).where(
                Follow.follower_id == collection.user_id,
                Follow.following_id == current_user.id,
            )
        )
        if not viewer_follows.scalar_one_or_none() or not owner_follows.scalar_one_or_none():
            raise HTTPException(
                status_code=403,
                detail="This collection is only visible to mutual followers",
            )


# ── Collection CRUD ───────────────────────────────────────────────────────────

@router.get("/", response_model=List[CollectionOut])
async def list_my_collections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .order_by(Collection.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = Collection(user_id=current_user.id, **payload.model_dump())
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = await _own_collection(collection_id, db, current_user)
    await db.delete(collection)
    await db.commit()


# ── Collection items ──────────────────────────────────────────────────────────

@router.get("/{collection_id}/samples", response_model=List[SampleOut])
async def get_collection_samples(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    result = await db.execute(
        select(Collection)
        .options(
            selectinload(Collection.samples).options(
                selectinload(Sample.audio_metadata),
                selectinload(Sample.tags),
            )
        )
        .where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    await _check_visibility(collection, current_user, db)
    return collection.samples


@router.post(
    "/{collection_id}/samples/{sample_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def add_to_collection(
    collection_id: uuid.UUID,
    sample_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = await _own_collection(collection_id, db, current_user)

    if not await db.get(Sample, sample_id):
        raise HTTPException(status_code=404, detail="Sample not found")

    existing = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.sample_id == sample_id,
        )
    )
    if existing.scalar_one_or_none():
        return  # idempotent

    # Atomic: add item + activity log in same transaction
    db.add(CollectionItem(collection_id=collection_id, sample_id=sample_id))
    db.add(UserActivity(
        user_id=current_user.id,
        activity_type="collection_add",
        sample_id=sample_id,
        activity_data={"collection_name": collection.name, "collection_id": str(collection_id)},
    ))
    await db.commit()


@router.delete(
    "/{collection_id}/samples/{sample_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_from_collection(
    collection_id: uuid.UUID,
    sample_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _own_collection(collection_id, db, current_user)
    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.sample_id == sample_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not in collection")
    await db.delete(item)
    await db.commit()
