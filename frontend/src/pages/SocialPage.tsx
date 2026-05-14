import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  followUser,
  unfollowUser,
  getFollowing,
  searchUsers,
  getFeed,
} from "../api/follows";
import { useAuthStore } from "../store/authStore";
import type { ActivityOut, UserPublic } from "../types";

const FEED_LIMIT = 30;

function formatActivityType(type: string): string {
  switch (type) {
    case "comment": return "commented on";
    case "rating": return "rated";
    case "collection_add": return "added to a collection";
    case "upload": return "uploaded";
    default: return type;
  }
}

export function SocialPage() {
  const { token, username: currentUsername } = useAuthStore();

  // ── friend search ──────────────────────────────────────────
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserPublic[]>([]);
  const [searching, setSearching] = useState(false);
  const [followingSet, setFollowingSet] = useState<Set<string>>(new Set());
  const [followLoading, setFollowLoading] = useState<Set<string>>(new Set());

  // ── activity feed ──────────────────────────────────────────
  const [feed, setFeed] = useState<ActivityOut[]>([]);
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedOffset, setFeedOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Load current user's following set so search results show correct button state
  useEffect(() => {
    if (!currentUsername) return;
    getFollowing(currentUsername, 200).then((users) => {
      setFollowingSet(new Set(users.map((u) => u.username)));
    });
  }, [currentUsername]);

  // Load feed
  useEffect(() => {
    if (!token) { setFeedLoading(false); return; }
    setFeedLoading(true);
    getFeed(FEED_LIMIT, feedOffset)
      .then((items) => {
        setFeed((prev) => feedOffset === 0 ? items : [...prev, ...items]);
        setHasMore(items.length === FEED_LIMIT);
      })
      .finally(() => setFeedLoading(false));
  }, [token, feedOffset]);

  // Debounced user search
  useEffect(() => {
    if (!query.trim()) { setResults([]); setSearching(false); return; }
    setSearching(true);
    const t = setTimeout(() => {
      searchUsers(query.trim())
        .then((users) => setResults(users.filter((u) => u.username !== currentUsername)))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [query, currentUsername]);

  const handleFollow = async (targetUsername: string) => {
    setFollowLoading((prev) => new Set([...prev, targetUsername]));
    try {
      if (followingSet.has(targetUsername)) {
        await unfollowUser(targetUsername);
        setFollowingSet((prev) => { const s = new Set(prev); s.delete(targetUsername); return s; });
      } else {
        await followUser(targetUsername);
        setFollowingSet((prev) => new Set([...prev, targetUsername]));
      }
    } finally {
      setFollowLoading((prev) => { const s = new Set(prev); s.delete(targetUsername); return s; });
    }
  };

  if (!token) {
    return (
      <div className="page">
        <p className="auth-prompt">
          <Link to="/login">Log in</Link> to find friends and see their activity.
        </p>
      </div>
    );
  }

  return (
    <div className="page social-page">
      <div className="social-layout">

        {/* ── Left: Find Friends ── */}
        <aside className="social-left">
          <h2 className="social-section-title">Find Friends</h2>
          <input
            type="search"
            className="social-search-input"
            placeholder="Search by username…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />

          {searching && <p className="social-hint">Searching…</p>}

          {!searching && query.trim() && results.length === 0 && (
            <p className="empty">No users found.</p>
          )}

          {results.length > 0 && (
            <ul className="user-search-results">
              {results.map((u) => (
                <li key={u.id} className="user-search-item">
                  <Link to={`/profile/${u.username}`} className="user-search-avatar">
                    {u.username[0].toUpperCase()}
                  </Link>
                  <Link to={`/profile/${u.username}`} className="user-search-name">
                    {u.username}
                  </Link>
                  <button
                    className={`follow-btn ${followingSet.has(u.username) ? "following" : ""}`}
                    onClick={() => handleFollow(u.username)}
                    disabled={followLoading.has(u.username)}
                  >
                    {followLoading.has(u.username)
                      ? "…"
                      : followingSet.has(u.username) ? "Following" : "Follow"}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!query.trim() && (
            <p className="social-hint">Type a username to find people to follow.</p>
          )}
        </aside>

        {/* ── Right: Friend Activity ── */}
        <section className="social-right">
          <h2 className="social-section-title">Friend Activity</h2>

          {!feedLoading && feed.length === 0 && (
            <p className="empty">
              No activity yet. Follow some users to see what they're up to.
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
                    <span className="activity-sample">{item.sample_title ?? "a sample"}</span>
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

          {feedLoading && <div className="loading">Loading…</div>}

          {!feedLoading && hasMore && (
            <button
              className="load-more-btn"
              onClick={() => setFeedOffset((o) => o + FEED_LIMIT)}
            >
              Load more
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
