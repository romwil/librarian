import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function PeoplePage() {
  const [users, setUsers] = useState([]);
  const [link, setLink] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .people()
      .then((data) => setUsers(data.users || []))
      .catch((err) => setError(err.message));
  }, []);

  async function mint(role) {
    setError("");
    try {
      const minted = await api.mintInvite(role);
      setLink(minted.join_url || minted.join_path);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="admin-room">
      <p className="eyebrow">Household</p>
      <h1>People</h1>
      <p className="lede">Invite-only. The raw token is shown once.</p>
      {error ? <p className="alert">{error}</p> : null}
      <div className="peek-acts">
        <button type="button" className="primary" onClick={() => mint("reader")}>
          Invite a reader
        </button>
        <button type="button" className="ghost" onClick={() => mint("op")}>
          Invite an op
        </button>
      </div>
      {link ? <p className="join-once">{link}</p> : null}
      <ul className="stack">
        {users.map((person) => (
          <li key={person.id} className="card">
            <strong>{person.display_name}</strong>
            <p className="muted">{person.role}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
