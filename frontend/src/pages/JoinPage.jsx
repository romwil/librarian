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
      eyebrow="Household library"
      title="The Reading Room"
      seal={invite ? role : null}
      lede="The same foyer as sign-in. Your role is sealed on the invite — you do not choose it."
      footer={<Link to="/login">Already have a key?</Link>}
    >
      {error ? <p className="alert">{error}</p> : null}
      {invite ? (
        <form className="login-form" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="join-name">Name</label>
            <input id="join-name" value={username} onChange={(e) => setUsername(e.target.value)} minLength={2} required />
          </div>
          <div className="field">
            <label htmlFor="join-pass">Password</label>
            <input
              id="join-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </div>
          <button type="submit" className="cta">
            Enter
          </button>
        </form>
      ) : null}
    </GlassDoor>
  );
}
