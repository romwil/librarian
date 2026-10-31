import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Alert from "../components/Alert.jsx";
import Field from "../components/Field.jsx";
import GlassDoor from "../components/GlassDoor.jsx";
import PasswordField from "../components/PasswordField.jsx";
import usePageTitle from "../hooks/usePageTitle.js";
import {
  FIELD_HELP,
  JOIN_LEDE,
  JOIN_PASTE_HINT,
  PAGE_TITLE_JOIN,
  formatInviteExpiry,
  humanError,
  inviteTokenFromInput,
} from "../copy.js";

export default function JoinPage() {
  const [params, setParams] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [paste, setPaste] = useState("");
  usePageTitle(PAGE_TITLE_JOIN);

  useEffect(() => {
    if (!token) {
      setInvite(null);
      setError("");
      return;
    }
    let cancelled = false;
    api
      .validateInvite(token)
      .then((data) => {
        if (cancelled) return;
        setInvite(data.invite);
        setError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setInvite(null);
        setError(humanError(err, "join"));
      });
    return () => {
      cancelled = true;
    };
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

  function onPasteSubmit(event) {
    event.preventDefault();
    const next = inviteTokenFromInput(paste);
    if (!next) {
      setError(humanError("Invite not found", "join"));
      return;
    }
    const query = new URLSearchParams(params);
    query.set("token", next);
    setParams(query);
  }

  const role = invite?.role === "op" ? "Helper" : "Reader";
  const expiry = invite?.expires_at ? formatInviteExpiry(invite.expires_at) : "";

  return (
    <main id="main" tabIndex={-1}>
      <GlassDoor
        eyebrow="Household library"
        title="The Reading Room"
        seal={invite ? role : null}
        lede={JOIN_LEDE}
        footer={<Link to="/login">Already have a key?</Link>}
      >
        {error ? <Alert>{error}</Alert> : null}
        {!token ? (
          <form className="login-form" onSubmit={onPasteSubmit}>
            <p className="lede">{JOIN_PASTE_HINT}</p>
            <div className="field">
              <label htmlFor="join-paste">Invite link</label>
              <input
                id="join-paste"
                value={paste}
                onChange={(event) => setPaste(event.target.value)}
                aria-label="Invite link"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <button type="submit" className="cta outline">
              Open invite
            </button>
          </form>
        ) : null}
        {invite ? (
          <form className="login-form" onSubmit={onSubmit}>
            {expiry ? <p className="muted">This invite expires {expiry}.</p> : null}
            <Field
              id="join-name"
              label="Name"
              help={FIELD_HELP.joinName}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              minLength={2}
              required
            />
            <PasswordField
              id="join-pass"
              label="Password"
              help={FIELD_HELP.joinPassword}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
            <button type="submit" className="cta">
              Enter
            </button>
          </form>
        ) : null}
      </GlassDoor>
    </main>
  );
}
