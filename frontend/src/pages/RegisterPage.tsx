import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export function RegisterPage() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const { register } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);

    const clientErrors: string[] = [];
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
      clientErrors.push("Email: Must be a valid email address.");
    if (username.length < 3)
      clientErrors.push("Username: Must be at least 3 characters.");
    if (password.length < 8)
      clientErrors.push("Password: Must be at least 8 characters.");
    if (clientErrors.length > 0) {
      setErrors(clientErrors);
      return;
    }

    setLoading(true);
    try {
      await register(email, username, password);
      navigate("/");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setErrors(
          detail.map((e: { msg?: string; loc?: string[] }) => {
            const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : "";
            const msg = e.msg ?? "Invalid value";
            return field
              ? `${field.charAt(0).toUpperCase() + field.slice(1)}: ${msg}`
              : msg;
          })
        );
      } else {
        setErrors([typeof detail === "string" ? detail : "Registration failed."]);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1>Create account</h1>
        <form onSubmit={handleSubmit}>
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
          <label>Username</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
          {errors.length > 0 && (
            <ul className="error-list">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
          <button type="submit" disabled={loading} className="submit-btn">
            {loading ? "Creating account…" : "Sign up"}
          </button>
        </form>
        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}
