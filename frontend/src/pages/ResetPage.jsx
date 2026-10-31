import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Alert from "../components/Alert.jsx";
import GlassDoor from "../components/GlassDoor.jsx";
import PasswordField from "../components/PasswordField.jsx";
import usePageTitle from "../hooks/usePageTitle.js";
import { FIELD_HELP, PAGE_TITLE_RESET, humanError } from "../copy.js";

export default function ResetPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  usePageTitle(PAGE_TITLE_RESET);

  useEffect(() => {
    if (!token) {
      setError(humanError("Reset link not found", "reset"));
      return;
    }
    api
      .validateReset(token)
      .then((data) => {
        setName(data.display_name || "");
        setReady(true);
        setError("");
      })
      .catch((err) => {
        setReady(false);
        setError(humanError(err, "reset"));
      });
  }, [token]);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.redeemReset(token, password);
      navigate("/");
    } catch (err) {
      setError(humanError(err, "reset"));
    }
  }

  return (
    <main id="main" tabIndex={-1}>
      <GlassDoor
        eyebrow="Household library"
        title="New key"
        lede={
          name
            ? `This replaces the password for ${name}. Other devices will need to sign in again.`
            : "Open the reset link from whoever runs the library. It lasts 24 hours and works once."
        }
        footer={<Link to="/login">Back to sign in</Link>}
      >
        {error ? <Alert>{error}</Alert> : null}
        {ready ? (
          <form className="login-form" onSubmit={onSubmit}>
            <PasswordField
              id="reset-pass"
              label="New password"
              help={FIELD_HELP.resetPassword}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
            />
            <button type="submit" className="cta">
              Set new password
            </button>
          </form>
        ) : null}
      </GlassDoor>
    </main>
  );
}
