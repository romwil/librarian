import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import Alert from "../components/Alert.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import WarmLoad from "../components/WarmLoad.jsx";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import {
  INVITE_OP_HELP,
  INVITE_OP_LABEL,
  INVITE_READER_LABEL,
  INVITE_SHOWN_ONCE,
  INVITE_TTL_HELP,
  PAGE_TITLE_PEOPLE,
  formatInviteExpiry,
  formatLastSignIn,
  humanError,
  inviteShareMessage,
} from "../copy.js";

export default function PeoplePage() {
  const { user, features } = useOutletContext() || {};
  const owner = user?.role === "owner";
  const [users, setUsers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [link, setLink] = useState("");
  const [share, setShare] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [resetLink, setResetLink] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [typedName, setTypedName] = useState("");
  useDocumentTitle(PAGE_TITLE_PEOPLE);

  function load() {
    return api
      .people()
      .then((data) => {
        setUsers(data.users || []);
        setInvites(data.invites || []);
        setLoading(false);
        setError("");
      })
      .catch((err) => {
        setError(humanError(err));
        setLoading(false);
      });
  }

  useEffect(() => {
    load();
  }, []);

  async function mint(role) {
    setError("");
    setCopied(false);
    try {
      const minted = await api.mintInvite(role);
      const url = minted.join_url || minted.join_path;
      setLink(url);
      setShare(
        inviteShareMessage({
          joinUrl: url,
          role,
          expiresLabel: formatInviteExpiry(minted.expires_at || minted.invite?.expires_at),
          householdName: features?.household_name,
        }),
      );
      await load();
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function revoke(inviteId) {
    setError("");
    try {
      await api.revokeInvite(inviteId);
      await load();
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function setRole(person, role) {
    setError("");
    try {
      await api.changeRole(person.id, role);
      await load();
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function setDisabled(person, disabled) {
    setError("");
    try {
      await api.disablePerson(person.id, disabled);
      await load();
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function issueReset(person) {
    setError("");
    setResetLink("");
    try {
      const issued = await api.issueReset(person.id);
      setResetLink(issued.reset_url || issued.reset_path);
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    if (typedName.trim() !== pendingDelete.display_name) {
      setError("Type the name exactly to delete this card.");
      return;
    }
    setError("");
    try {
      await api.deletePerson(pendingDelete.id);
      setPendingDelete(null);
      setTypedName("");
      await load();
    } catch (err) {
      setError(humanError(err));
    }
  }

  return (
    <div className="admin-room page-settle">
      <p className="kicker">Household</p>
      <h1>People</h1>
      <p className="lede">{INVITE_TTL_HELP}</p>
      {error ? <Alert>{error}</Alert> : null}
      <div className="cta-row">
        <button type="button" className="cta" onClick={() => mint("reader")}>
          {INVITE_READER_LABEL}
        </button>
        {owner ? (
          <button type="button" className="cta ghost" onClick={() => mint("op")}>
            {INVITE_OP_LABEL}
          </button>
        ) : null}
      </div>
      {owner ? <p className="muted">{INVITE_OP_HELP}</p> : null}
      <ConfirmDialog
        open={Boolean(link)}
        title={INVITE_SHOWN_ONCE}
        cancelLabel="Done"
        onCancel={() => {
          setLink("");
          setShare("");
          setCopied(false);
        }}
        testId="invite-dialog"
      >
        <p className="join-once">{link}</p>
        <div className="cta-row">
          <button type="button" className="cta outline" onClick={() => copyText(link)}>
            Copy
          </button>
          {share ? (
            <button type="button" className="cta ghost" onClick={() => copyText(share)}>
              Copy message
            </button>
          ) : null}
        </div>
        {copied ? (
          <p className="muted" role="status">
            Copied.
          </p>
        ) : null}
      </ConfirmDialog>
      {resetLink ? (
        <div className="invite-once">
          <p className="lede">Reset link (shown once, lasts 24 hours):</p>
          <p className="join-once">{resetLink}</p>
          <button type="button" className="cta outline" onClick={() => copyText(resetLink)}>
            Copy
          </button>
        </div>
      ) : null}
      {loading ? <WarmLoad message="Warming the lamp on the household roll…" testId="people-loading" /> : null}
      {!loading && invites.length ? (
        <section className="people-pending">
          <h2>Pending invites</h2>
          <ul className="stack">
            {invites.map((invite) => (
              <li key={invite.id} className="card">
                <strong>{invite.role === "op" ? "Helper" : "Reader"}</strong>
                <p className="muted">Expires {formatInviteExpiry(invite.expires_at)}</p>
                <button type="button" className="cta ghost" onClick={() => revoke(invite.id)}>
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {!loading ? (
        <ul className="stack">
          {users.map((person) => {
            const paused = Boolean(person.disabled);
            const isOwner = person.role === "owner";
            const isSelf = person.id === user?.id;
            return (
              <li key={person.id} className="card">
                <strong>
                  {person.display_name}
                  {paused ? " (paused)" : ""}
                </strong>
                <p className="muted">
                  {person.role}
                  {" · "}
                  {formatLastSignIn(person.last_login_at)}
                </p>
                {owner && !isOwner && !isSelf ? (
                  <div className="cta-row people-actions">
                    {person.role === "reader" ? (
                      <button type="button" className="cta ghost" onClick={() => setRole(person, "op")}>
                        Make helper
                      </button>
                    ) : (
                      <button type="button" className="cta ghost" onClick={() => setRole(person, "reader")}>
                        Make reader
                      </button>
                    )}
                    <button
                      type="button"
                      className="cta ghost"
                      onClick={() => setDisabled(person, !paused)}
                    >
                      {paused ? "Resume card" : "Pause card"}
                    </button>
                    <button type="button" className="cta ghost" onClick={() => issueReset(person)}>
                      Send reset
                    </button>
                    <button type="button" className="cta ghost" onClick={() => setPendingDelete(person)}>
                      Delete
                    </button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this library card?"
        confirmLabel="Delete card"
        onCancel={() => {
          setPendingDelete(null);
          setTypedName("");
        }}
        onConfirm={confirmDelete}
        testId="people-delete-confirm"
      >
        <p>
          This removes {pendingDelete?.display_name}’s progress, shelves, whispers, and notices from the live
          database. Type the name to confirm.
        </p>
        <div className="field">
          <label htmlFor="people-delete-name">Name</label>
          <input
            id="people-delete-name"
            value={typedName}
            onChange={(event) => setTypedName(event.target.value)}
            autoComplete="off"
          />
        </div>
      </ConfirmDialog>
    </div>
  );
}
