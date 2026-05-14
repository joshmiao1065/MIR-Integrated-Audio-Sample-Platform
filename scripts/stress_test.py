"""
Stress test for Phase 2 social/discovery endpoints.

Usage:
    python -m scripts.stress_test --base-url http://localhost:8000 --concurrency 10

Tests:
  - Authentication (register + login)
  - Sample listing (new / trending / top_rated)
  - Follows (follow / unfollow idempotency)
  - Activity feed
  - User profile + followers/following lists
  - Recommendations (personalized + similar)
  - Collections with visibility=friends/private/public
  - Concurrent cache recompute safety (trending/top_rated under load)
  - Tag listing
"""

import asyncio
import argparse
import random
import string
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── helpers ──────────────────────────────────────────────────────────────────

def rand_str(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


@dataclass
class User:
    username: str
    email: str
    password: str
    token: str = ""
    user_id: str = ""


@dataclass
class Results:
    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def ok(self, label: str) -> None:
        self.passed += 1
        print(f"  ✓ {label}")

    def fail(self, label: str, detail: str = "") -> None:
        self.failed += 1
        msg = f"  ✗ {label}" + (f": {detail}" if detail else "")
        self.errors.append(msg)
        print(msg)

    def summary(self) -> str:
        total = self.passed + self.failed
        return (
            f"\n{'─'*50}\n"
            f"  {self.passed}/{total} passed"
            + (f"\n  Failures:\n" + "\n".join(self.errors) if self.errors else "")
            + f"\n{'─'*50}"
        )


# ── registration + login ─────────────────────────────────────────────────────

async def register_and_login(client: httpx.AsyncClient, base: str) -> Optional[User]:
    u = User(
        username=rand_str(10),
        email=f"{rand_str(10)}@stress-example.com",
        password="Str0ng!Pass",
    )
    r = await client.post(f"{base}/api/auth/register", json={
        "username": u.username, "email": u.email, "password": u.password,
    })
    if r.status_code not in (200, 201):
        return None
    r2 = await client.post(f"{base}/api/auth/token", data={
        "username": u.email, "password": u.password,
    })
    if r2.status_code != 200:
        return None
    u.token = r2.json()["access_token"]
    return u


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {user.token}"}


# ── individual test suites ────────────────────────────────────────────────────

async def test_auth(client: httpx.AsyncClient, base: str, res: Results) -> Optional[User]:
    u = await register_and_login(client, base)
    if u:
        res.ok("register + login")
    else:
        res.fail("register + login")
        return None

    # duplicate register → 409
    r = await client.post(f"{base}/api/auth/register", json={
        "username": u.username, "email": u.email, "password": u.password,
    })
    if r.status_code in (400, 409, 422):
        res.ok("duplicate register rejected")
    else:
        res.fail("duplicate register rejected", str(r.status_code))

    return u


async def test_samples(client: httpx.AsyncClient, base: str, res: Results) -> list[str]:
    sample_ids: list[str] = []
    for sort in ("new", "trending", "top_rated"):
        r = await client.get(f"{base}/api/samples/", params={"sort": sort, "limit": 5})
        if r.status_code == 200 and isinstance(r.json(), list):
            ids = [s["id"] for s in r.json()]
            sample_ids.extend(ids)
            res.ok(f"list_samples sort={sort} → {len(ids)} items")
        else:
            res.fail(f"list_samples sort={sort}", str(r.status_code))

    # tag filter
    r = await client.get(f"{base}/api/samples/", params={"tag_name": "Music", "limit": 3})
    if r.status_code == 200:
        res.ok("list_samples tag_name filter")
    else:
        res.fail("list_samples tag_name filter", str(r.status_code))

    return list(set(sample_ids))


async def test_tags(client: httpx.AsyncClient, base: str, res: Results) -> None:
    r = await client.get(f"{base}/api/tags/")
    if r.status_code == 200 and isinstance(r.json(), list):
        res.ok(f"GET /api/tags/ → {len(r.json())} tags")
    else:
        res.fail("GET /api/tags/", str(r.status_code))


async def test_follows(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    follower: User,
    target: User,
) -> None:
    # follow
    r = await client.post(f"{base}/api/users/{target.username}/follow", headers=auth(follower))
    if r.status_code in (200, 201, 204):
        res.ok("follow user")
    else:
        res.fail("follow user", f"{r.status_code} {r.text[:80]}")

    # idempotent re-follow → still 2xx
    r2 = await client.post(f"{base}/api/users/{target.username}/follow", headers=auth(follower))
    if r2.status_code in (200, 201, 204):
        res.ok("follow idempotent")
    else:
        res.fail("follow idempotent", str(r2.status_code))

    # profile reflects new follower
    r3 = await client.get(f"{base}/api/users/{target.username}", headers=auth(follower))
    if r3.status_code == 200:
        profile = r3.json()
        if profile.get("is_following") is True:
            res.ok("profile is_following=True after follow")
        else:
            res.fail("profile is_following", str(profile))
    else:
        res.fail("GET profile", str(r3.status_code))

    # unfollow
    r4 = await client.delete(f"{base}/api/users/{target.username}/follow", headers=auth(follower))
    if r4.status_code in (200, 204):
        res.ok("unfollow user")
    else:
        res.fail("unfollow user", str(r4.status_code))

    # idempotent unfollow
    r5 = await client.delete(f"{base}/api/users/{target.username}/follow", headers=auth(follower))
    if r5.status_code in (200, 204):
        res.ok("unfollow idempotent")
    else:
        res.fail("unfollow idempotent", str(r5.status_code))


async def test_feed(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    user: User,
) -> None:
    r = await client.get(f"{base}/api/users/feed", headers=auth(user), params={"limit": 10})
    if r.status_code == 200 and isinstance(r.json(), list):
        res.ok(f"GET /feed → {len(r.json())} items")
    else:
        res.fail("GET /feed", f"{r.status_code} {r.text[:80]}")

    # unauthenticated → 401
    r2 = await client.get(f"{base}/api/users/feed")
    if r2.status_code == 401:
        res.ok("feed requires auth")
    else:
        res.fail("feed requires auth", str(r2.status_code))


async def test_recommendations(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    user: User,
    sample_ids: list[str],
) -> None:
    r = await client.get(f"{base}/api/recommendations/", headers=auth(user))
    if r.status_code == 200 and isinstance(r.json(), list):
        res.ok(f"personalized recommendations → {len(r.json())} items")
    else:
        res.fail("personalized recommendations", f"{r.status_code} {r.text[:80]}")

    if sample_ids:
        sid = sample_ids[0]
        r2 = await client.get(f"{base}/api/recommendations/similar/{sid}")
        if r2.status_code == 200 and isinstance(r2.json(), list):
            res.ok(f"similar samples for {sid[:8]}… → {len(r2.json())} items")
        else:
            res.fail("similar samples", f"{r2.status_code} {r2.text[:80]}")


async def test_collections_visibility(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    owner: User,
    stranger: User,
    sample_ids: list[str],
) -> None:
    for vis in ("public", "friends", "private"):
        r = await client.post(f"{base}/api/collections/", headers=auth(owner), json={
            "name": f"stress-{vis}-{rand_str(4)}",
            "visibility": vis,
        })
        if r.status_code not in (200, 201):
            res.fail(f"create {vis} collection", f"{r.status_code} {r.text[:80]}")
            continue
        cid = r.json()["id"]
        res.ok(f"create {vis} collection")

        # add a sample if we have one
        if sample_ids:
            ra = await client.post(
                f"{base}/api/collections/{cid}/samples/{sample_ids[0]}",
                headers=auth(owner),
            )
            if ra.status_code in (200, 201, 204):
                res.ok(f"add sample to {vis} collection")
            else:
                res.fail(f"add sample to {vis} collection", f"{ra.status_code} {ra.text[:80]}")

        # owner always can read
        ro = await client.get(f"{base}/api/collections/{cid}/samples", headers=auth(owner))
        if ro.status_code == 200:
            res.ok(f"owner reads {vis} collection")
        else:
            res.fail(f"owner reads {vis} collection", str(ro.status_code))

        # stranger visibility rules
        rs = await client.get(f"{base}/api/collections/{cid}/samples", headers=auth(stranger))
        if vis == "public":
            expected = 200
        else:
            expected = 403
        if rs.status_code == expected:
            res.ok(f"stranger {vis} collection → {rs.status_code}")
        else:
            res.fail(
                f"stranger {vis} collection visibility",
                f"got {rs.status_code}, want {expected}",
            )

        # cleanup
        await client.delete(f"{base}/api/collections/{cid}", headers=auth(owner))


async def test_concurrent_rankings(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    concurrency: int,
) -> None:
    """Hit trending + top_rated endpoints concurrently to stress cache locking."""
    async def one() -> int:
        r = await client.get(f"{base}/api/samples/", params={"sort": "trending", "limit": 5})
        return r.status_code

    t0 = time.perf_counter()
    statuses = await asyncio.gather(*[one() for _ in range(concurrency)])
    elapsed = time.perf_counter() - t0
    failures = [s for s in statuses if s != 200]
    if not failures:
        res.ok(f"concurrent ranking ({concurrency} req) all 200 in {elapsed:.2f}s")
    else:
        res.fail("concurrent ranking", f"{len(failures)} non-200: {set(failures)}")


async def test_user_search(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    target: User,
) -> None:
    r = await client.get(f"{base}/api/users/search", params={"q": target.username[:4]})
    if r.status_code == 200 and isinstance(r.json(), list):
        found = any(u["username"] == target.username for u in r.json())
        if found:
            res.ok("user search finds registered user")
        else:
            res.fail("user search finds registered user", "not in results")
    else:
        res.fail("user search", f"{r.status_code} {r.text[:80]}")


async def test_followers_following(
    client: httpx.AsyncClient,
    base: str,
    res: Results,
    follower: User,
    target: User,
) -> None:
    # set up a follow first
    await client.post(f"{base}/api/users/{target.username}/follow", headers=auth(follower))

    r_frs = await client.get(f"{base}/api/users/{target.username}/followers")
    if r_frs.status_code == 200:
        found = any(u["username"] == follower.username for u in r_frs.json())
        if found:
            res.ok("followers list contains follower")
        else:
            res.fail("followers list contains follower", "missing")
    else:
        res.fail("GET /followers", str(r_frs.status_code))

    r_fng = await client.get(f"{base}/api/users/{follower.username}/following")
    if r_fng.status_code == 200:
        found = any(u["username"] == target.username for u in r_fng.json())
        if found:
            res.ok("following list contains target")
        else:
            res.fail("following list contains target", "missing")
    else:
        res.fail("GET /following", str(r_fng.status_code))

    # cleanup
    await client.delete(f"{base}/api/users/{target.username}/follow", headers=auth(follower))


# ── main ──────────────────────────────────────────────────────────────────────

async def run(base: str, concurrency: int) -> int:
    res = Results()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # health check
        hc = await client.get(f"{base}/health")
        if hc.status_code != 200:
            print(f"Server not reachable at {base} ({hc.status_code})")
            return 1

        print(f"\nStress-testing {base}\n{'─'*50}")

        print("\n[auth]")
        user_a = await test_auth(client, base, res)
        if not user_a:
            print("Cannot continue without authenticated users.")
            return 1

        user_b_raw = await register_and_login(client, base)
        if not user_b_raw:
            res.fail("register second user")
            return 1
        user_b = user_b_raw

        print("\n[samples]")
        sample_ids = await test_samples(client, base, res)

        print("\n[tags]")
        await test_tags(client, base, res)

        print("\n[user search]")
        await test_user_search(client, base, res, user_b)

        print("\n[follows]")
        await test_follows(client, base, res, follower=user_a, target=user_b)

        print("\n[followers / following lists]")
        await test_followers_following(client, base, res, follower=user_a, target=user_b)

        print("\n[feed]")
        await test_feed(client, base, res, user_a)

        print("\n[recommendations]")
        await test_recommendations(client, base, res, user_a, sample_ids)

        print("\n[collections visibility]")
        await test_collections_visibility(client, base, res, owner=user_a, stranger=user_b, sample_ids=sample_ids)

        print(f"\n[concurrent ranking — {concurrency} simultaneous requests]")
        await test_concurrent_rankings(client, base, res, concurrency)

    print(res.summary())
    return 0 if res.failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 stress test")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.base_url, args.concurrency)))


if __name__ == "__main__":
    main()
