import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export function Navbar() {
  const { username, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <nav className="navbar">
      <Link to="/" className="nav-brand">
        SampleLib
      </Link>
      <div className="nav-links">
        <Link to="/browse">Browse</Link>
        {username && <Link to="/feed">Feed</Link>}
        {username && <Link to="/collections">Collections</Link>}
        {username && <Link to="/upload">Upload</Link>}
        {username ? (
          <>
            <Link to={`/profile/${username}`} className="nav-username">{username}</Link>
            <button onClick={handleLogout} className="nav-btn">Log out</button>
          </>
        ) : (
          <>
            <Link to="/login">Log in</Link>
            <Link to="/register" className="nav-btn">Sign up</Link>
          </>
        )}
      </div>
    </nav>
  );
}
