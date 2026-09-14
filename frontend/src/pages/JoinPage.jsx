import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import GlassDoor from "../components/GlassDoor.jsx";

export default function JoinPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (!token) {
      setError("Invite not found");
      return;
    }
    api
      .validateInvite(token)
      .then((data) => setInvite(data.invite))
      .catch((err) => setError(err.message || "Invite not found"));
  }, [token]);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.redeem(token, username, password);
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not join");
    }
  }

  const role = invite?.role === "op" ? "Op" : "Reader";

  return (
    <GlassDoor
      eyebrow={invite ? role : "Join"}
      title="Join this household"
      lede="The same foyer as sign-in. Your role is sealed on the invite — you do not choose it."
      footer={<Link to="/login">Already have a key?</Link>}
    >
      {error ? <p className="alert">{error}</p> : null}
      {invite ? (
        <form className="login-form" onSubmit={onSubmit}>
          <p className="login-help">You are joining as a {role}.</p>
          <label className="login-field">
            Display name
            <input value={username} onChange={(e) => setUsername(e.target.value)} minLength={2} required />
          </label>
          <label className="login-field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <button type="submit" className="login-primary">
            Take a shelf
          </button>
        </form>
      ) : null}
    </GlassDoor>
  );
}
