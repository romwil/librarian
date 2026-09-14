import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import GlassDoor from "../components/GlassDoor.jsx";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.login(username, password);
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not sign in");
    }
  }

  return (
    <GlassDoor
      eyebrow="Librarian"
      title="The foyer"
      lede="A night reading room for the household stacks. Sign in to walk The Hall."
      footer={<Link to="/join">Have a join link?</Link>}
    >
      {error ? <p className="alert">{error}</p> : null}
      <form className="login-form" onSubmit={onSubmit}>
        <label className="login-field">
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label className="login-field">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <button type="submit" className="login-primary">
          Open the door
        </button>
      </form>
    </GlassDoor>
  );
}
