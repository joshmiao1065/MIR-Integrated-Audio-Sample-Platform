import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { followUser, getFollowers, getFollowing, getUserActivity, unfollowUser } from "../api/follows";
import { getUserSamples } from "../api/samples";
import { useAuthStore } from "../store/authStore";
import { SampleCard } from "../components/SampleCard";
import type { ActivityOut, Sample, UserProfile, UserPublic } from "../types";

type ProfileTab = "activity" | "uploads" | "followers" | "following";

function formatActivityType(type: string): string {
  switch (type) {
    case "comment": return "commented on";
    case "rating": return "rated";
    case "collection_add": return "added to a collection";
    case "upload": return "uploaded";
    default: return type;
  }
}

export function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { username: currentUsername, token } = useAuthStore();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [followers, setFollowers] = useState<UserPublic[]>([]);
  const [following, setFollowing] = useState<UserPublic[]>([]);
  const [activity, setActivity] = useState<ActivityOut[]>([]);
  const [uploads, setUploads] = useState<Sample[]>([]);
  const [loading, setLoading] = useState(true);
  const [followLoading, setFollowLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<ProfileTab>("activity");

  useEffect(() => {
    if (!username) return;
    setLoading(true);
    setError("");

    // Fetch profile data from the users router
    const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
    const h: HeadersInit = {};
    const storedToken = localStorage.getItem("access_token");
    if (storedToken) h["Authorization"] = `Bearer ${storedToken}`;

    Promise.all([
      fetch(`${base}/api/users/${username}`, { headers: h }).then((r) => r.ok ? r.json() : Promise.reject(r)),
      getFollowers(username, 100),
      getFollowing(username, 100),
      getUserActivity(username),
      getUserSamples(username),
    ])
      .then(([p, frs, fng, act, ups]) => {
        setProfile(p);
        setFollowers(frs);
        setFollowing(fng);
        setActivity(act);
        setUploads(ups);
      })
      .catch(() => setError("User not found."))
      .finally(() => setLoading(false));
  }, [username]);

  const handleFollow = async () => {
    if (!profile || !username) return;
    setFollowLoading(true);
    try {
      if (profile.is_following) {
        await unfollowUser(username);
        setProfile((p) => p ? { ...p, is_following: false, follower_count: p.follower_count - 1 } : p);
        setFollowers((prev) => prev.filter((u) => u.username !== currentUsername));
      } else {
        await followUser(username);
        setProfile((p) => p ? { ...p, is_following: true, follower_count: p.follower_count + 1 } : p);
      }
    } finally {
      setFollowLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading…</div>;
  if (error || !profile) return <div className="error">{error || "User not found."}</div>;

  const isSelf = currentUsername === username;

  return (
    <div className="page profile-page">
      {/* ── Header ── */}
      <div className="profile-header">
        <div className="profile-avatar">{profile.username[0].toUpperCase()}</div>
        <div className="profile-info">
          <h1 className="profile-username">{profile.username}</h1>
          <div className="profile-stats">
            <button className="profile-stat-btn" onClick={() => setActiveTab("followers")}>
              <strong>{profile.follower_count}</strong> followers
            </button>
            <button className="profile-stat-btn" onClick={() => setActiveTab("following")}>
              <strong>{profile.following_count}</strong> following
            </button>
          </div>
          <p className="profile-joined">Joined {new Date(profile.created_at).toLocaleDateString()}</p>
        </div>
        {token && !isSelf && (
          <button
            className={`follow-btn ${profile.is_following ? "following" : ""}`}
            onClick={handleFollow}
            disabled={followLoading}
          >
            {followLoading ? "…" : profile.is_following ? "Following" : "Follow"}
          </button>
        )}
      </div>

      {/* ── Tabs ── */}
      <div className="social-tabs">
        <button
          className={`social-tab ${activeTab === "activity" ? "active" : ""}`}
          onClick={() => setActiveTab("activity")}
        >
          Activity
        </button>
        <button
          className={`social-tab ${activeTab === "uploads" ? "active" : ""}`}
          onClick={() => setActiveTab("uploads")}
        >
          Uploads ({uploads.length})
        </button>
        <button
          className={`social-tab ${activeTab === "followers" ? "active" : ""}`}
          onClick={() => setActiveTab("followers")}
        >
          Followers ({profile.follower_count})
        </button>
        <button
          className={`social-tab ${activeTab === "following" ? "active" : ""}`}
          onClick={() => setActiveTab("following")}
        >
          Following ({profile.following_count})
        </button>
      </div>

      {/* ── Activity ── */}
      {activeTab === "activity" && (
        <div>
          {activity.length === 0 ? (
            <p className="empty">No activity yet.</p>
          ) : (
            <div className="activity-list-full">
              {activity.map((item) => (
                <div key={item.id} className="activity-item-full">
                  <div className="activity-main">
                    <span className="activity-verb">{formatActivityType(item.activity_type)} </span>
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
          )}
        </div>
      )}

      {/* ── Uploads ── */}
      {activeTab === "uploads" && (
        <div>
          {uploads.length === 0 ? (
            <p className="empty">No uploads yet.</p>
          ) : (
            <div className="sample-grid">
              {uploads.map((s) => <SampleCard key={s.id} sample={s} />)}
            </div>
          )}
        </div>
      )}

      {/* ── Followers ── */}
      {activeTab === "followers" && (
        <div>
          {followers.length === 0 ? (
            <p className="empty">No followers yet.</p>
          ) : (
            <ul className="social-user-list">
              {followers.map((u) => (
                <li key={u.id} className="social-user-item">
                  <Link to={`/profile/${u.username}`} className="user-search-avatar">
                    {u.username[0].toUpperCase()}
                  </Link>
                  <Link to={`/profile/${u.username}`} className="user-search-name">
                    {u.username}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Following ── */}
      {activeTab === "following" && (
        <div>
          {following.length === 0 ? (
            <p className="empty">Not following anyone yet.</p>
          ) : (
            <ul className="social-user-list">
              {following.map((u) => (
                <li key={u.id} className="social-user-item">
                  <Link to={`/profile/${u.username}`} className="user-search-avatar">
                    {u.username[0].toUpperCase()}
                  </Link>
                  <Link to={`/profile/${u.username}`} className="user-search-name">
                    {u.username}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
