import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import PasswordField from "../components/PasswordField.jsx";
import Rail from "../components/Rail.jsx";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import {
  ACCOUNT_HEADING,
  CHANGE_PASSWORD,
  EXPORT_MY_CARD,
  FIELD_HELP,
  OPDS_COPIED,
  OPDS_COPY,
  OPDS_HEADING,
  OPDS_LEDE,
  PAGE_TITLE_CARD,
  PRIVACY_HEADING,
  SIGN_OUT_EVERYWHERE,
  YOUR_ASKS,
  emptyLibraryCardCopy,
  humanError,
} from "../copy.js";
import { continueRailItems } from "../hallRails.js";

export default function CardPage() {
  const { user } = useOutletContext();
  const navigate = useNavigate();
  const [card, setCard] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [accountNote, setAccountNote] = useState("");
  const [opdsUrl, setOpdsUrl] = useState("");
  const [opdsNote, setOpdsNote] = useState("");
  useDocumentTitle(PAGE_TITLE_CARD);

  useEffect(() => {
    let cancelled = false;
    api
      .libraryCard()
      .then((data) => {
        if (cancelled) return;
        setCard(data);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError(humanError(err));
      });
    api
      .privacy()
      .then((data) => {
        if (!cancelled) setNotice(data);
      })
      .catch(() => {});
    api
      .opds()
      .then((data) => {
        if (!cancelled) setOpdsUrl(String(data?.catalog_url || ""));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const reading = continueRailItems(card?.continue);
  const listening = continueRailItems(card?.continue_listening);
  const finished = continueRailItems(card?.finished);
  const favorites = continueRailItems(card?.favorites);
  const wantedCount = Number(card?.wanted_count || 0);
  const asks = Array.isArray(card?.asks) ? card.asks : [];
  const empty = emptyLibraryCardCopy();
  const hasRails = Boolean(listening || reading || finished || favorites || asks.length);

  async function onChangePassword(event) {
    event.preventDefault();
    setAccountNote("");
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setAccountNote("Password saved. Other devices will need to sign in again.");
    } catch (err) {
      setAccountNote(humanError(err));
    }
  }

  async function onSignOutEverywhere() {
    setAccountNote("");
    try {
      await api.signOutEverywhere();
      navigate("/login");
    } catch (err) {
      setAccountNote(humanError(err));
    }
  }

  async function onCopyOpds() {
    setOpdsNote("");
    try {
      const data = await api.opds();
      const url = String(data?.catalog_url || "");
      if (!url) return;
      setOpdsUrl(url);
      await navigator.clipboard.writeText(url);
      setOpdsNote(OPDS_COPIED);
    } catch (err) {
      setOpdsNote(humanError(err));
    }
  }

  async function onExport() {
    setAccountNote("");
    try {
      const data = await api.exportCard();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "librarian-card.json";
      anchor.click();
      URL.revokeObjectURL(url);
      setAccountNote("Exported a copy of this card.");
    } catch (err) {
      setAccountNote(humanError(err));
    }
  }

  return (
    <div className="hall page-settle" data-testid="library-card">
      <header className="browse-hero">
        <p className="kicker">Library card</p>
        <h1>Your library</h1>
      </header>
      {error ? (
        <p className="alert" role="alert" aria-live="assertive">
          {error}
        </p>
      ) : null}
      {card && !error && !hasRails ? (
        <section className="empty-cta" data-testid="library-card-empty">
          <h2>{empty.title}</h2>
          <p className="lede">{empty.lede}</p>
          <Link className="cta" to={empty.href}>
            {empty.cta}
          </Link>
        </section>
      ) : null}
      {listening ? <Rail title="Continue listening" items={listening} role={user?.role} /> : null}
      {reading ? <Rail title="Continue reading" items={reading} role={user?.role} /> : null}
      {finished ? <Rail title="Recently finished" items={finished} role={user?.role} /> : null}
      {favorites ? (
        <Rail title="Favorites" items={favorites} seeAllTo={browseHref({ shelf: "favorites" })} role={user?.role} />
      ) : null}
      <p className="lede" style={{ padding: "0 var(--gutter)" }}>
        <Link to="/wanted">Wanted</Link>
        {wantedCount ? ` · ${wantedCount}` : ""}
      </p>
      {asks.length ? (
        <section className="card-panel" data-testid="your-asks">
          <p className="kicker">{YOUR_ASKS}</p>
          <h2>Looking and waiting</h2>
          <ul className="noted-books">
            {asks.map((ask) => (
              <li key={ask.id || ask.title}>
                {ask.href ? <Link to={ask.href}>{ask.title}</Link> : ask.title}
                {ask.label ? <span className="muted"> · {ask.label}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card-panel" id="opds" data-testid="opds-panel">
        <p className="kicker">{OPDS_HEADING}</p>
        <h2>Catalog link</h2>
        <p className="lede">{OPDS_LEDE}</p>
        {opdsUrl ? (
          <p className="lede" data-testid="opds-catalog-url">
            <code>{opdsUrl}</code>
          </p>
        ) : null}
        {opdsNote ? (
          <p className="alert" role="status">
            {opdsNote}
          </p>
        ) : null}
        <button type="button" className="cta outline" onClick={onCopyOpds}>
          {OPDS_COPY}
        </button>
      </section>
      <section className="card-panel" id="comfort">
        <p className="kicker">Comfort</p>
        <h2>Lights and type</h2>
        <p className="lede">Theme, text size, and the lamp live on the Library card menu in the top bar.</p>
      </section>
      <section className="card-panel" id="accessibility">
        <p className="kicker">Accessibility</p>
        <h2>A quieter door</h2>
        <p className="lede">
          Unique page titles, announced sign-in errors, and a show-password control are on. A fuller accessibility
          pass lands later.
        </p>
      </section>
      <section className="card-panel" id="privacy" data-testid="privacy-panel">
        <p className="kicker">{PRIVACY_HEADING}</p>
        <h2>{notice?.title || "How this household library treats your card"}</h2>
        {(notice?.paragraphs || []).map((paragraph) => (
          <p key={paragraph} className="lede">
            {paragraph}
          </p>
        ))}
      </section>
      <section className="card-panel" id="account" data-testid="account-panel">
        <p className="kicker">{ACCOUNT_HEADING}</p>
        <h2>Your key</h2>
        {accountNote ? (
          <p className="alert" role="status">
            {accountNote}
          </p>
        ) : null}
        <form className="login-form" onSubmit={onChangePassword}>
          <PasswordField
            id="card-current-pass"
            label="Current password"
            help={FIELD_HELP.currentPassword}
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
          />
          <PasswordField
            id="card-new-pass"
            label="New password"
            help={FIELD_HELP.newPassword}
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
          />
          <button type="submit" className="cta">
            {CHANGE_PASSWORD}
          </button>
        </form>
        <div className="cta-row">
          <button type="button" className="cta outline" onClick={onExport}>
            {EXPORT_MY_CARD}
          </button>
          <button type="button" className="cta ghost" onClick={onSignOutEverywhere}>
            {SIGN_OUT_EVERYWHERE}
          </button>
        </div>
      </section>
    </div>
  );
}
