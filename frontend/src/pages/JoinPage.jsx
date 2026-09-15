import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import GlassDoor from "../components/GlassDoor.jsx";
import { FIELD_HELP, humanError } from "../copy.js";

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
      setError(humanError("Invite not found", "join"));
      return;
    }
    api
      .validateInvite(token)
      .then((data) => setInvite(data.invite))
      .catch((err) => setError(humanError(err, "join")));
  }, [token]);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.redeem(token, username, password);
      navigate("/");
    } catch (err) {
      setError(humanError(err, "join"));
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
            <FieldLabel htmlFor="join-name" label="Name" help={FIELD_HELP.joinName} />
            <input id="join-name" value={username} onChange={(e) => setUsername(e.target.value)} minLength={2} required />
          </div>
          <div className="field">
            <FieldLabel htmlFor="join-pass" label="Password" help={FIELD_HELP.joinPassword} />
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
