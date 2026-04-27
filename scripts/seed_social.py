#!/usr/bin/env python3
"""
Populate the social tables with realistic demo data for presentation.

Creates fake users, then seeds ratings, comments, collections, and download
history referencing those users and the real samples already in the database.
Comments are generated from tag/BPM context so they read as authentic.

All seed accounts use email format  seed_<username>@samplelib.demo  so they
can be cleanly removed without touching real users.

Usage:
    # Install the one extra dep first (not in requirements.txt):
    pip install faker

    # Seed with defaults (10 users, random seed 42):
    python -m scripts.seed_social

    # Custom user count / reproducible run:
    python -m scripts.seed_social --users 8 --seed 123

    # Preview what would be inserted without touching the DB:
    python -m scripts.seed_social --dry-run

    # Remove all seeded data (deletes users whose email ends @samplelib.demo):
    python -m scripts.seed_social --clear
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from faker import Faker
except ImportError:
    print("ERROR: faker is not installed.  Run:  pip install faker")
    sys.exit(1)

from passlib.context import CryptContext
from sqlalchemy import delete, select, text

from app.database import AsyncSessionLocal
from app.models.collection import Collection, CollectionItem
from app.models.sample import Sample
from app.models.social import Comment, Rating
from app.models.system import DownloadHistory
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SEED_DOMAIN = "@samplelib.demo"
_bcrypt = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Comment templates ─────────────────────────────────────────────────────────

_YAMNET_COMMENTS = [
    "love the {tag} on this",
    "that {tag} texture is clean",
    "{tag} hits exactly right",
    "perfect {tag} sample, zero noise",
    "this {tag} is going straight in the crate",
    "the {tag} sits well in the mix",
    "clean {tag}, no bleed",
]
_MUSICNN_COMMENTS = [
    "{tag} vibes all the way",
    "perfect for {tag} production",
    "very {tag} — works well layered",
    "top tier {tag} sample",
    "this {tag} loops without phasing",
]
_BPM_COMMENTS = [
    "running this at {bpm} BPM, fits perfectly",
    "{bpm} BPM is the sweet spot for this one",
    "tight at {bpm} — going in the drum rack",
    "half-time at {bpm} works too, very flexible",
]
_KEY_COMMENTS = [
    "love the {key} on this, very versatile",
    "easy to layer in {key}",
    "{key} sits well over minor progressions",
]
_GENERIC_COMMENTS = [
    "instantly sampled this",
    "this slaps",
    "clean sample, no bleed",
    "been looking for something like this",
    "certified heat",
    "added to the crate",
    "crispy. in the session now",
    "underrated find, gonna flip this",
    "this loops perfectly",
    "low-end is immaculate",
    "layered this with 808s — works perfectly",
    "going in every project for the next month",
    "textured perfectly, easy to chop",
    "exactly the vibe I was looking for",
]

# ── Collection themes ─────────────────────────────────────────────────────────

# (tag_keyword_to_match, collection_name, description)
_THEMED_COLLECTIONS = [
    ("drum",        "Drum Rack Essentials",   "Core drum sounds for any session"),
    ("bass",        "Low End Theory",         "Sub bass, bass guitar, and 808s"),
    ("piano",       "Keys Collection",        "Piano loops and keyboard textures"),
    ("guitar",      "Guitar Textures",        "Acoustic and electric guitar samples"),
    ("string",      "String Sessions",        "Orchestral strings and ensemble sounds"),
    ("synth",       "Synth Selects",          "Synthesizer leads, pads, and arps"),
    ("vocal",       "Vocal Chops",            "Processed vocals and voice samples"),
    ("ambient",     "Ambient Textures",       "Atmospheric pads and soundscapes"),
    ("electronic",  "Electronic Experiments", "Electronic percussion and effects"),
    ("hip hop",     "Hip-Hop Fundamentals",   "Breaks, chops, and classic hip-hop sounds"),
    ("jazz",        "Jazz Samples",           "Jazz instruments and ensemble recordings"),
    ("percussion",  "Percussion Toolkit",     "Shakers, claps, toms, and more"),
]
_GENERIC_COLLECTIONS = [
    ("My Sample Pack",     "Personal sample selection"),
    ("Session Starters",   "Go-to sounds for starting a new track"),
    ("The Vault",          "Archived gems from deep dives"),
    ("Late Night Session", "Dark and moody sounds for late-night work"),
    ("Work in Progress",   "Samples I'm currently using in projects"),
    ("Reference Tracks",   "Useful for A/B comparison"),
    ("Inspiration Folder", "Sounds that spark new ideas"),
    ("Crate Diggin",       "Found samples and hidden gems"),
]

# ── Rating distribution (skewed positive — producers save what they like) ─────
_RATING_SCORES  = [1, 2, 3, 4, 5]
_RATING_WEIGHTS = [3, 7, 15, 35, 40]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rand_past_dt(rng: random.Random, days: int = 60) -> datetime:
    """Return a random UTC datetime within the past `days` days."""
    delta = timedelta(seconds=rng.randint(0, days * 86400))
    return datetime.now(timezone.utc) - delta


def _pick_comment(rng: random.Random, tags: list[tuple[str, str]], bpm, key) -> str:
    """Build a contextual comment string from sample metadata."""
    yamnet_tags = [n for n, c in tags if c == "yamnet"]
    musicnn_tags = [n for n, c in tags if c == "musicnn"]

    options: list[str] = []

    if yamnet_tags:
        tmpl = rng.choice(_YAMNET_COMMENTS)
        options.append(tmpl.format(tag=rng.choice(yamnet_tags)))

    if musicnn_tags:
        tmpl = rng.choice(_MUSICNN_COMMENTS)
        options.append(tmpl.format(tag=rng.choice(musicnn_tags)))

    if bpm is not None:
        tmpl = rng.choice(_BPM_COMMENTS)
        options.append(tmpl.format(bpm=round(bpm, 1)))

    if key is not None:
        tmpl = rng.choice(_KEY_COMMENTS)
        options.append(tmpl.format(key=key))

    options.append(rng.choice(_GENERIC_COMMENTS))

    return rng.choice(options)


def _match_theme(tags: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Return (name, description) for the first matching themed collection, or None."""
    tag_names = {n.lower() for n, _ in tags}
    for keyword, name, desc in _THEMED_COLLECTIONS:
        if any(keyword in t for t in tag_names):
            return name, desc
    return None


# ── Core phases ───────────────────────────────────────────────────────────────

async def _clear(dry_run: bool) -> None:
    """Delete all users whose email ends with @samplelib.demo (cascades ratings/collections)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email.like(f"%{_SEED_DOMAIN}"))
        )
        users = result.scalars().all()
        if not users:
            log.info("No seed users found — nothing to clear.")
            return
        log.info("Clearing %d seed user(s)…", len(users))
        if not dry_run:
            await db.execute(
                delete(User).where(User.email.like(f"%{_SEED_DOMAIN}"))
            )
            await db.commit()
            log.info("Done. (Comments with SET NULL user_id remain; harmless.)")
        else:
            log.info("[dry-run] Would delete %d user(s).", len(users))


async def _ensure_users(
    db,
    n: int,
    fake: Faker,
    rng: random.Random,
    pw_hash: str,
) -> list[User]:
    """Get-or-create seed users. Skips usernames that are already taken."""
    existing = (
        await db.execute(select(User).where(User.email.like(f"%{_SEED_DOMAIN}")))
    ).scalars().all()
    if existing:
        log.info("Found %d existing seed user(s), reusing.", len(existing))
        return list(existing)

    users: list[User] = []
    seen_usernames: set[str] = set()

    for _ in range(n * 3):  # oversample to handle collisions
        if len(users) >= n:
            break
        username = fake.user_name().lower().replace(".", "_")[:30]
        if username in seen_usernames:
            continue
        seen_usernames.add(username)
        email = f"seed_{username}{_SEED_DOMAIN}"
        u = User(
            id=uuid.uuid4(),
            email=email,
            username=username,
            hashed_password=pw_hash,
            is_active=True,
        )
        db.add(u)
        users.append(u)

    await db.flush()
    log.info("Created %d seed user(s).", len(users))
    return users


async def _query_samples(db, limit: int = 200) -> list[dict]:
    """Return processed samples as plain dicts (avoids DetachedInstanceError later)."""
    rows = await db.execute(
        text("""
            SELECT
                s.id,
                am.bpm,
                am.key,
                am.energy_level,
                COALESCE(
                    json_agg(json_build_object('name', t.name, 'category', t.category))
                        FILTER (WHERE t.id IS NOT NULL),
                    '[]'
                ) AS tags
            FROM samples s
            LEFT JOIN audio_metadata am ON am.sample_id = s.id
            LEFT JOIN sample_tags st ON st.sample_id = s.id
            LEFT JOIN tags t ON t.id = st.tag_id
            GROUP BY s.id, am.bpm, am.key, am.energy_level
            ORDER BY random()
            LIMIT :limit
        """),
        {"limit": limit},
    )
    samples = []
    for row in rows.mappings():
        tags_raw = row["tags"] or []
        # asyncpg returns json_agg as a list, but may return a string in some
        # Supabase connection configs — handle both safely.
        if isinstance(tags_raw, str):
            tags_raw = json.loads(tags_raw)
        tag_list = [(t["name"], t["category"]) for t in tags_raw]
        samples.append({
            "id": row["id"],
            "bpm": row["bpm"],
            "key": row["key"],
            "energy_level": row["energy_level"],
            "tags": tag_list,
        })
    return samples


def _plan_ratings(
    users: list[User],
    samples: list[dict],
    rng: random.Random,
) -> list[dict]:
    """Each user rates ~35% of the sample pool."""
    rows = []
    for user in users:
        n = max(1, int(len(samples) * rng.uniform(0.25, 0.45)))
        chosen = rng.sample(samples, min(n, len(samples)))
        for s in chosen:
            rows.append({
                "id": uuid.uuid4(),
                "user_id": user.id,
                "sample_id": s["id"],
                "score": rng.choices(_RATING_SCORES, weights=_RATING_WEIGHTS, k=1)[0],
                "created_at": _rand_past_dt(rng),
            })
    return rows


def _plan_comments(
    users: list[User],
    samples: list[dict],
    rng: random.Random,
) -> list[dict]:
    """~45% of samples get 1–3 comments from random users."""
    n_commented = max(1, int(len(samples) * 0.45))
    commented = rng.sample(samples, min(n_commented, len(samples)))
    rows = []
    for s in commented:
        n_comments = rng.choices([1, 2, 3], weights=[55, 30, 15], k=1)[0]
        commenters = rng.sample(users, min(n_comments, len(users)))
        for user in commenters:
            rows.append({
                "id": uuid.uuid4(),
                "user_id": user.id,
                "sample_id": s["id"],
                "text": _pick_comment(rng, s["tags"], s["bpm"], s["key"]),
                "created_at": _rand_past_dt(rng),
            })
    return rows


def _plan_collections(
    users: list[User],
    samples: list[dict],
    rng: random.Random,
) -> list[dict]:
    """1–2 collections per user, themed by tag when possible."""
    rows = []
    for user in users:
        n = rng.randint(1, 2)
        used_names: set[str] = set()

        for _ in range(n):
            # Try to find an unused theme
            theme_candidates = list(_THEMED_COLLECTIONS) + [
                (None, name, desc) for name, desc in _GENERIC_COLLECTIONS
            ]
            rng.shuffle(theme_candidates)

            col_name = col_desc = None
            theme_keyword = None
            for keyword, name, desc in theme_candidates:
                if name not in used_names:
                    theme_keyword = keyword
                    col_name = name
                    col_desc = desc
                    used_names.add(name)
                    break

            if col_name is None:
                continue

            # Filter samples by theme keyword
            if theme_keyword:
                pool = [
                    s for s in samples
                    if any(theme_keyword in tag_name.lower() for tag_name, _ in s["tags"])
                ]
            else:
                pool = samples

            if len(pool) < 3:
                pool = samples  # fall back to full pool

            n_items = min(rng.randint(8, 15), len(pool))
            chosen_items = rng.sample(pool, n_items)

            coll_id = uuid.uuid4()
            rows.append({
                "collection": {
                    "id": coll_id,
                    "user_id": user.id,
                    "name": col_name,
                    "description": col_desc,
                    "is_private": False,
                    "created_at": _rand_past_dt(rng, days=30),
                },
                "items": [
                    {"collection_id": coll_id, "sample_id": s["id"], "added_at": _rand_past_dt(rng, days=20)}
                    for s in chosen_items
                ],
            })
    return rows


def _plan_downloads(
    users: list[User],
    samples: list[dict],
    rng: random.Random,
    n: int = 80,
) -> list[dict]:
    """Spread `n` download events across users and samples."""
    rows = []
    for _ in range(n):
        rows.append({
            "id": uuid.uuid4(),
            "user_id": rng.choice(users).id,
            "sample_id": rng.choice(samples)["id"],
            "downloaded_at": _rand_past_dt(rng, days=45),
        })
    return rows


async def _insert_all(
    ratings: list[dict],
    comments: list[dict],
    collections: list[dict],
    downloads: list[dict],
    dry_run: bool,
) -> None:
    if dry_run:
        log.info(
            "[dry-run] Would insert: %d ratings, %d comments, %d collections, %d downloads.",
            len(ratings), len(comments), len(collections), len(downloads),
        )
        return

    async with AsyncSessionLocal() as db:
        # Ratings — ON CONFLICT DO NOTHING (unique constraint user+sample)
        for r in ratings:
            await db.execute(
                text("""
                    INSERT INTO ratings (id, user_id, sample_id, score, created_at)
                    VALUES (:id, :user_id, :sample_id, :score, :created_at)
                    ON CONFLICT (user_id, sample_id) DO NOTHING
                """),
                r,
            )

        # Comments
        for c in comments:
            db.add(Comment(
                id=c["id"],
                user_id=c["user_id"],
                sample_id=c["sample_id"],
                text=c["text"],
                created_at=c["created_at"],
            ))

        # Collections + items — IDs generated in Python so no flush needed mid-loop
        for entry in collections:
            c = entry["collection"]
            db.add(Collection(
                id=c["id"],
                user_id=c["user_id"],
                name=c["name"],
                description=c["description"],
                is_private=c["is_private"],
                created_at=c["created_at"],
            ))
            for item in entry["items"]:
                db.add(CollectionItem(
                    collection_id=item["collection_id"],
                    sample_id=item["sample_id"],
                    added_at=item["added_at"],
                ))

        # Download history
        for d in downloads:
            db.add(DownloadHistory(
                id=d["id"],
                user_id=d["user_id"],
                sample_id=d["sample_id"],
                downloaded_at=d["downloaded_at"],
            ))

        await db.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> None:
    if args.clear:
        await _clear(args.dry_run)
        return

    rng = random.Random(args.seed)
    fake = Faker()
    fake.seed_instance(args.seed)

    # Hash password once before opening the session (bcrypt is slow)
    log.info("Hashing seed password…")
    pw_hash = _bcrypt.hash("demo1234")

    # Phase 1: create/fetch users + query sample pool
    async with AsyncSessionLocal() as db:
        users = await _ensure_users(db, args.users, fake, rng, pw_hash)
        await db.commit()
        log.info("Querying sample pool…")
        samples = await _query_samples(db, limit=200)

    if not samples:
        log.error("No samples found in the database. Ingest some samples first.")
        sys.exit(1)

    log.info("Sample pool: %d samples (%d have tags).",
             len(samples), sum(1 for s in samples if s["tags"]))

    # Phase 2: plan all inserts (pure Python, no DB)
    ratings   = _plan_ratings(users, samples, rng)
    comments  = _plan_comments(users, samples, rng)
    colls     = _plan_collections(users, samples, rng)
    downloads = _plan_downloads(users, samples, rng)

    log.info(
        "Plan: %d ratings, %d comments, %d collections (%d items), %d downloads.",
        len(ratings),
        len(comments),
        len(colls),
        sum(len(e["items"]) for e in colls),
        len(downloads),
    )

    # Phase 3: insert everything
    await _insert_all(ratings, comments, colls, downloads, args.dry_run)

    if not args.dry_run:
        log.info("Done! Social tables populated.")
        log.info("All seed accounts use password: demo1234")
        log.info("Remove seed data later with: python -m scripts.seed_social --clear")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users",   type=int, default=10, help="Number of fake user accounts to create (default: 10)")
    parser.add_argument("--seed",    type=int, default=42,  help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--dry-run", action="store_true",   help="Print what would be inserted without touching the DB")
    parser.add_argument("--clear",   action="store_true",   help="Delete all seeded users and their data, then exit")
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
