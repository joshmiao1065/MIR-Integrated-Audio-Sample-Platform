"""Tag-based TF-IDF recommendation engine.

Builds a weighted tag preference profile from a user's ratings, downloads, and
collection additions, then scores candidate samples by the sum of matching TF-IDF
weights.  All logic is a single SQL CTE — no extra ML infrastructure needed.

Engagement weights
------------------
  rating 5 → 3.0,  rating 4 → 2.0,  rating 3 → 1.0
  rating 2 → -0.3, rating 1 → -0.5  (mild dislike signals)
  download → 1.5,  collection_add → 2.0

IDF
---
  LN(total_samples / samples_with_that_tag)
  Generic tags ("Music", appearing on 90% of samples) get IDF ≈ 0.1.
  Specific tags ("Kick drum", on 5% of samples) get IDF ≈ 3.0.

Cold start
----------
  Returns None when the user has no engagement history or when all candidate
  scores are zero.  The caller falls back to weekly_trending in that case.
"""
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_RECOMMENDATION_SQL = """
WITH user_engagement AS (
    SELECT sample_id, SUM(weight) AS total_weight
    FROM (
        SELECT sample_id,
            CASE score
                WHEN 5 THEN 3.0
                WHEN 4 THEN 2.0
                WHEN 3 THEN 1.0
                WHEN 2 THEN -0.3
                WHEN 1 THEN -0.5
            END AS weight
        FROM ratings
        WHERE user_id = :user_id

        UNION ALL

        SELECT DISTINCT sample_id, 1.5 AS weight
        FROM download_history
        WHERE user_id = :user_id

        UNION ALL

        SELECT ci.sample_id, 2.0 AS weight
        FROM collection_items ci
        JOIN collections c ON ci.collection_id = c.id
        WHERE c.user_id = :user_id
    ) raw
    GROUP BY sample_id
),
total_docs AS (
    SELECT COUNT(*)::float AS n FROM samples
),
tag_idf AS (
    SELECT tag_id,
        LN((SELECT n FROM total_docs) / NULLIF(COUNT(DISTINCT sample_id), 0)) AS idf
    FROM sample_tags
    GROUP BY tag_id
),
user_tag_weights AS (
    SELECT t.id AS tag_id, t.name,
        SUM(ue.total_weight) * COALESCE(ti.idf, 0) AS tfidf_weight
    FROM user_engagement ue
    JOIN sample_tags st ON st.sample_id = ue.sample_id
    JOIN tags t ON t.id = st.tag_id
    JOIN tag_idf ti ON ti.tag_id = t.id
    WHERE t.category IN ('yamnet', 'musicnn')
    GROUP BY t.id, t.name, ti.idf
    HAVING SUM(ue.total_weight) * COALESCE(ti.idf, 0) > 0
),
candidate_scores AS (
    SELECT
        st.sample_id,
        SUM(utw.tfidf_weight) AS relevance_score,
        ARRAY_AGG(utw.name ORDER BY utw.tfidf_weight DESC) AS matching_tags
    FROM sample_tags st
    JOIN user_tag_weights utw ON st.tag_id = utw.tag_id
    WHERE st.sample_id NOT IN (SELECT sample_id FROM user_engagement)
    GROUP BY st.sample_id
    ORDER BY relevance_score DESC
    LIMIT 50
)
SELECT sample_id, relevance_score, matching_tags[1:3] AS top_tags
FROM candidate_scores
"""

_SIMILAR_SQL = """
SELECT st.sample_id, COUNT(*) AS overlap
FROM sample_tags st
WHERE
    st.tag_id IN (SELECT tag_id FROM sample_tags WHERE sample_id = :sample_id)
    AND st.sample_id != :sample_id
GROUP BY st.sample_id
ORDER BY overlap DESC
LIMIT 6
"""


async def get_recommendations(
    db: AsyncSession, user_id: uuid.UUID
) -> Optional[List[Tuple[uuid.UUID, float, List[str]]]]:
    """
    Returns list of (sample_id, relevance_score, top_matching_tags) or None on cold-start.
    """
    rows = await db.execute(text(_RECOMMENDATION_SQL), {"user_id": user_id})
    results = rows.all()
    if not results:
        return None
    return [(r[0], float(r[1]), list(r[2] or [])) for r in results]


async def get_similar_sample_ids(
    db: AsyncSession, sample_id: uuid.UUID
) -> List[uuid.UUID]:
    rows = await db.execute(text(_SIMILAR_SQL), {"sample_id": sample_id})
    return [r[0] for r in rows.all()]
