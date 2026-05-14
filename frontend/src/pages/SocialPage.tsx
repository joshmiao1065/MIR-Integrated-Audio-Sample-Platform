import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  followUser,
  unfollowUser,
  removeFollower,
  getFollowers,
  getFollowing,
  searchUsers,
  getFeed,
} from "../api/follows";
import { useAuthStore } from "../store/authStore";
import type { ActivityOut, UserPublic } from "../types";

const FEED_LIMIT = 30;
type Tab = "activity" | "following" | "followers";

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

  // ── tab state ──────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>("activity");

  // ── user search ────────────────────────────────────────────
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserPublic[]>([]);
  const [searching, setSearching] = useState(false);

  // ── following list (who I follow) ──────────────────────────
  const [following, setFollowing] = useState<UserPublic[]>([]);
  const [followingLoading, setFollowingLoading] = useState(true);

  // ── followers list (who follows me) ───────────────────────
  const [followers, setFollowers] = useState<UserPublic[]>([]);
  const [followersLoading, setFollowersLoading] = useState(true);

  // set of usernames I follow — kept in sync across all three lists
  const [followingSet, setFollowingSet] = useState<Set<string>>(new Set());

  // per-username loading guards
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set());

  // ── activity feed ──────────────────────────────────────────
  const [feed, setFeed] = useState<ActivityOut[]>([]);
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedOffset, setFeedOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Load following + followers on mount
  useEffect(() => {
    if (!currentUsername || !token) return;

    getFollowing(currentUsername, 200)
      .then((users) => {
        setFollowing(users);
        setFollowingSet(new Set(users.map((u) => u.username)));
      })
      .finally(() => setFollowingLoading(false));

    getFollowers(currentUsername, 200)
      .then(setFollowers)
      .finally(() => setFollowersLoading(false));
  }, [currentUsername, token]);

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

  // Debounced search
  useEffect(() => {
    if (!query.trim()) { setSearchResults([]); setSearching(false); return; }
    setSearching(true);
    const t = setTimeout(() => {
      searchUsers(query.trim())
        .then((users) => setSearchResults(users.filter((u) => u.username !== currentUsername)))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [query, currentUsername]);

  // ── action helpers ─────────────────────────────────────────

  const lock = (username: string) =>
    setActionLoading((prev) => new Set([...prev, username]));
  const unlock = (username: string) =>
    setActionLoading((prev) => { const s = new Set(prev); s.delete(username); return s; });

  const handleFollow = async (targetUsername: string) => {
    lock(targetUsername);
    try {
      if (followingSet.has(targetUsername)) {
        await unfollowUser(targetUsername);
        setFollowingSet((prev) => { const s = new Set(prev); s.delete(targetUsername); return s; });
        setFollowing((prev) => prev.filter((u) => u.username !== targetUsername));
      } else {
        await followUser(targetUsername);
        setFollowingSet((prev) => new Set([...prev, targetUsername]));
        // add to following list if not already there
        const found = searchResults.find((u) => u.username === targetUsername)
          ?? followers.find((u) => u.username === targetUsername);
        if (found) setFollowing((prev) => [found, ...prev]);
      }
    } finally {
      unlock(targetUsername);
    }
  };

  const handleRemoveFollower = async (targetUsername: string) => {
    lock(targetUsername);
    try {
      await removeFollower(targetUsername);
      setFollowers((prev) => prev.filter((u) => u.username !== targetUsername));
    } finally {
      unlock(targetUsername);
    }
  };

  // ── auth gate ──────────────────────────────────────────────

  if (!token) {
    return (
      <div className="page">
        <p className="auth-prompt">
          <Link to="/login">Log in</Link> to find and follow other users.
        </p>
      </div>
    );
  }

  // ── render ─────────────────────────────────────────────────

  return (
    <div className="page social-page">
      <div className="social-layout">

        {/* ── Left: Find People ─────────────────────────────── */}
        <aside className="social-left">
          <h2 className="social-section-title">Find People</h2>
          <input
            type="search"
            className="social-search-input"
            placeholder="Search by username…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          {searching && <p className="social-hint">Searching…</p>}

          {!searching && query.trim() && searchResults.length === 0 && (
            <p className="empty">No users found.</p>
          )}

          {searchResults.length > 0 && (
            <ul className="user-search-results">
              {searchResults.map((u) => (
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
                    disabled={actionLoading.has(u.username)}
                  >
                    {actionLoading.has(u.username) ? "…"
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

        {/* ── Right: Tabbed content ──────────────────────────── */}
        <section className="social-right">
          <div className="social-tabs">
            <button
              className={`social-tab ${activeTab === "activity" ? "active" : ""}`}
              onClick={() => setActiveTab("activity")}
            >
              Activity
            </button>
            <button
              className={`social-tab ${activeTab === "following" ? "active" : ""}`}
              onClick={() => setActiveTab("following")}
            >
              Following{!followingLoading && ` (${following.length})`}
            </button>
            <button
              className={`social-tab ${activeTab === "followers" ? "active" : ""}`}
              onClick={() => setActiveTab("followers")}
            >
              Followers{!followersLoading && ` (${followers.length})`}
            </button>
          </div>

          {/* Activity Feed */}
          {activeTab === "activity" && (
            <>
              {!feedLoading && feed.length === 0 && (
                <p className="empty">
                  No activity yet — follow some users to see what they're up to.
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
                <button className="load-more-btn" onClick={() => setFeedOffset((o) => o + FEED_LIMIT)}>
                  Load more
                </button>
              )}
            </>
          )}

          {/* Following */}
          {activeTab === "following" && (
            <>
              {followingLoading && <div className="loading">Loading…</div>}
              {!followingLoading && following.length === 0 && (
                <p className="empty">You're not following anyone yet. Search for users on the left.</p>
              )}
              <ul className="social-user-list">
                {following.map((u) => (
                  <li key={u.id} className="social-user-item">
                    <Link to={`/profile/${u.username}`} className="user-search-avatar">
                      {u.username[0].toUpperCase()}
                    </Link>
                    <Link to={`/profile/${u.username}`} className="user-search-name">
                      {u.username}
                    </Link>
                    <button
                      className="follow-btn following"
                      onClick={() => handleFollow(u.username)}
                      disabled={actionLoading.has(u.username)}
                    >
                      {actionLoading.has(u.username) ? "…" : "Unfollow"}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* Followers */}
          {activeTab === "followers" && (
            <>
              {followersLoading && <div className="loading">Loading…</div>}
              {!followersLoading && followers.length === 0 && (
                <p className="empty">No one is following you yet.</p>
              )}
              <ul className="social-user-list">
                {followers.map((u) => (
                  <li key={u.id} className="social-user-item">
                    <Link to={`/profile/${u.username}`} className="user-search-avatar">
                      {u.username[0].toUpperCase()}
                    </Link>
                    <Link to={`/profile/${u.username}`} className="user-search-name">
                      {u.username}
                    </Link>
                    <div className="social-follower-actions">
                      {/* Follow back if not already following */}
                      {!followingSet.has(u.username) && (
                        <button
                          className="follow-btn"
                          onClick={() => handleFollow(u.username)}
                          disabled={actionLoading.has(u.username)}
                        >
                          {actionLoading.has(u.username) ? "…" : "Follow back"}
                        </button>
                      )}
                      {followingSet.has(u.username) && (
                        <span className="mutual-badge">Mutual</span>
                      )}
                      <button
                        className="remove-follower-btn"
                        onClick={() => handleRemoveFollower(u.username)}
                        disabled={actionLoading.has(u.username)}
                        title="Remove this follower"
                      >
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
