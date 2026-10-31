import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import GlassDoor from "../components/GlassDoor.jsx";
import PasswordField from "../components/PasswordField.jsx";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import {
  FIELD_HELP,
  FOYER_LEDE,
  FOYER_PASTE_LABEL,
  JOIN_PASTE_HINT,
  PAGE_TITLE_SIGN_IN,
  humanError,
  inviteTokenFromInput,
} from "../copy.js";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [paste, setPaste] = useState("");
  const [error, setError] = useState("");
  useDocumentTitle(PAGE_TITLE_SIGN_IN);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.login(username, password);
      navigate("/");
    } catch (err) {
      setError(humanError(err, "login"));
    }
  }

  function onPasteSubmit(event) {
    event.preventDefault();
    const next = inviteTokenFromInput(paste);
    if (!next) {
      setError(humanError("Invite not found", "join"));
      return;
    }
    navigate(`/join?token=${encodeURIComponent(next)}`);
  }

  return (
    <main id="main" tabIndex={-1}>
      <GlassDoor
        eyebrow="Household library"
        title="The Reading Room"
        lede={FOYER_LEDE}
        footer={<Link to="/join">Got an invite link?</Link>}
      >
        {error ? (
          <p className="alert" role="alert" aria-live="assertive">
            {error}
          </p>
        ) : null}
        <form className="login-form" onSubmit={onSubmit}>
          <div className="field">
            <FieldLabel htmlFor="login-name" label="Name" help={FIELD_HELP.loginName} />
            <input
              id="login-name"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <PasswordField
            id="login-pass"
            label="Password"
            help={FIELD_HELP.loginPassword}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button type="submit" className="cta">
            Enter
          </button>
        </form>
        <form className="login-form foyer-paste" onSubmit={onPasteSubmit}>
          <p className="lede">{JOIN_PASTE_HINT}</p>
          <div className="field">
            <label htmlFor="foyer-paste">{FOYER_PASTE_LABEL}</label>
            <input
              id="foyer-paste"
              value={paste}
              onChange={(event) => setPaste(event.target.value)}
              aria-label={FOYER_PASTE_LABEL}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <button type="submit" className="cta outline">
            Open invite
          </button>
        </form>
      </GlassDoor>
    </main>
  );
}
