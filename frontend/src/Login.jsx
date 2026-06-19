import { useState } from "react";
import { useAuth } from "./AuthContext";

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [interests, setInterests] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, interests);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>Travel Assistant</h1>
        <p className="auth-subtitle">
          Sign in to save your conversations and get personalized travel advice across all your devices.
        </p>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${mode === "login" ? "auth-tab--active" : ""}`}
            onClick={() => { setMode("login"); setError(""); }}
          >
            Log in
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === "register" ? "auth-tab--active" : ""}`}
            onClick={() => { setMode("register"); setError(""); }}
          >
            Sign up
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label">
            Email
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </label>

          <label className="auth-label">
            Password
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              required
              minLength={6}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>

          {mode === "register" && (
            <label className="auth-label">
              Travel interests
              <span className="auth-optional"> optional</span>
              <input
                type="text"
                className="auth-input"
                value={interests}
                onChange={(e) => setInterests(e.target.value)}
                placeholder="museums, hiking, vegetarian food, budget travel"
              />
            </label>
          )}

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" className="btn-primary auth-submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
