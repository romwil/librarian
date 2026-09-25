import { useEffect, useState } from "react";
import { api } from "../api.js";
import WarmLoad from "../components/WarmLoad.jsx";
import { humanError } from "../copy.js";

export default function PeoplePage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [link, setLink] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .people()
      .then((data) => {
        setUsers(data.users || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(humanError(err));
        setLoading(false);
      });
  }, []);

  async function mint(role) {
    setError("");
    try {
      const minted = await api.mintInvite(role);
      setLink(minted.join_url || minted.join_path);
    } catch (err) {
      setError(humanError(err));
    }
  }

  return (
    <div className="admin-room page-settle">
      <p className="kicker">Household</p>
      <h1>People</h1>
      <p className="lede">Invite-only. The raw token is shown once.</p>
      {error ? <p className="alert">{error}</p> : null}
      <div className="cta-row">
        <button type="button" className="cta" onClick={() => mint("reader")}>
          Invite a reader
        </button>
        <button type="button" className="cta ghost" onClick={() => mint("op")}>
          Invite an op
        </button>
      </div>
      {link ? <p className="join-once">{link}</p> : null}
      {loading ? <WarmLoad message="Warming the lamp on the household roll…" testId="people-loading" /> : null}
      {!loading ? (
        <ul className="stack">
          {users.map((person) => (
            <li key={person.id} className="card">
              <strong>{person.display_name}</strong>
              <p className="muted">{person.role}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
