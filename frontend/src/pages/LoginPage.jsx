import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import GlassDoor from "../components/GlassDoor.jsx";
import { FIELD_HELP, humanError } from "../copy.js";

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
      setError(humanError(err, "login"));
    }
  }

  return (
    <GlassDoor
      eyebrow="Household library"
      title="The Reading Room"
      lede="A quiet door. No covers of household titles on the glass — only lamp light and paper dust."
      footer={<Link to="/join">Have a join link?</Link>}
    >
      {error ? <p className="alert">{error}</p> : null}
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
        <div className="field">
          <FieldLabel htmlFor="login-pass" label="Password" help={FIELD_HELP.loginPassword} />
          <input
            id="login-pass"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <button type="submit" className="cta">
          Enter
        </button>
      </form>
    </GlassDoor>
  );
}
