import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getFeed } from "../api/follows";
import { useAuthStore } from "../store/authStore";
import type { ActivityOut } from "../types";

const LIMIT = 30;

function formatActivityType(type: string): string {
  switch (type) {
    case "comment": return "commented on";
    case "rating": return "rated";
    case "collection_add": return "added to a collection";
    case "upload": return "uploaded";
    default: return type;
  }
}

export function FeedPage() {
  const { token } = useAuthStore();
  const [feed, setFeed] = useState<ActivityOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    getFeed(LIMIT, offset)
      .then((items) => {
        setFeed((prev) => offset === 0 ? items : [...prev, ...items]);
        setHasMore(items.length === LIMIT);
      })
      .finally(() => setLoading(false));
  }, [token, offset]);

  if (!token) {
    return (
      <div className="page">
        <p className="auth-prompt"><Link to="/login">Log in</Link> to see your friends' activity.</p>
      </div>
    );
  }

  return (
    <div className="page feed-page">
      <h1>Friend Activity</h1>

      {feed.length === 0 && !loading && (
        <p className="empty">
          No activity yet. <Link to="/browse">Find users</Link> to follow.
        </p>
      )}

      <div className="activity-list-full">
        {feed.map((item) => (
          <div key={item.id} className="activity-item-full">
            <div className="activity-main">
              <Link to={`/profile/${item.username}`} className="activity-username">
                {item.username}
              </Link>
              <span className="activity-verb"> {formatActivityType(item.activity_type)} </span>
              {item.sample_id ? (
                <Link to={`/samples/${item.sample_id}`} className="activity-sample">
                  {item.sample_title ?? "a sample"}
                </Link>
              ) : (
                <span className="activity-sample">{item.sample_title}</span>
              )}
              {item.activity_type === "rating" && item.activity_data && (
                <span className="activity-score"> — {item.activity_data.score}★</span>
              )}
              {item.activity_type === "comment" && item.activity_data?.comment_preview && (
                <span className="activity-preview"> — "{item.activity_data.comment_preview}"</span>
              )}
              {item.activity_type === "collection_add" && item.activity_data?.collection_name && (
                <span className="activity-collection"> → {item.activity_data.collection_name}</span>
              )}
            </div>
            <span className="activity-time">
              {new Date(item.created_at).toLocaleString()}
            </span>
          </div>
        ))}
      </div>

      {loading && <div className="loading">Loading…</div>}

      {!loading && hasMore && (
        <button className="load-more-btn" onClick={() => setOffset((o) => o + LIMIT)}>
          Load more
        </button>
      )}
    </div>
  );
}
