import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { followUser, getFollowers, getFollowing, getUserProfile, unfollowUser } from "../api/follows";
import { useAuthStore } from "../store/authStore";
import type { UserProfile, UserPublic } from "../types";

export function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { username: currentUsername, token } = useAuthStore();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [followers, setFollowers] = useState<UserPublic[]>([]);
  const [following, setFollowing] = useState<UserPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [followLoading, setFollowLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!username) return;
    setLoading(true);
    Promise.all([
      getUserProfile(username),
      getFollowers(username),
      getFollowing(username),
    ])
      .then(([p, frs, fng]) => {
        setProfile(p);
        setFollowers(frs);
        setFollowing(fng);
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
      <div className="profile-header">
        <div className="profile-avatar">{profile.username[0].toUpperCase()}</div>
        <div className="profile-info">
          <h1 className="profile-username">{profile.username}</h1>
          <div className="profile-stats">
            <span><strong>{profile.follower_count}</strong> followers</span>
            <span><strong>{profile.following_count}</strong> following</span>
          </div>
          <p className="profile-joined">
            Joined {new Date(profile.created_at).toLocaleDateString()}
          </p>
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

      <div className="profile-lists">
        <div className="profile-list-section">
          <h3>Followers ({profile.follower_count})</h3>
          {followers.length === 0 ? (
            <p className="empty">No followers yet.</p>
          ) : (
            <ul className="user-list">
              {followers.map((u) => (
                <li key={u.id}>
                  <Link to={`/profile/${u.username}`}>{u.username}</Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="profile-list-section">
          <h3>Following ({profile.following_count})</h3>
          {following.length === 0 ? (
            <p className="empty">Not following anyone.</p>
          ) : (
            <ul className="user-list">
              {following.map((u) => (
                <li key={u.id}>
                  <Link to={`/profile/${u.username}`}>{u.username}</Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
