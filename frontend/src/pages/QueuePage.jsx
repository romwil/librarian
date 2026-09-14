import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function QueuePage() {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");

  function reload() {
    api
      .queue()
      .then((data) => setJobs(data.jobs || []))
      .catch((err) => setError(err.message));
  }

  useEffect(reload, []);

  return (
    <div className="admin-room">
      <p className="eyebrow">Exceptions</p>
      <h1>Queue</h1>
      <p className="lede">Living chips live on search cards. This list is for asked slips and SAB jobs.</p>
      {error ? <p className="alert">{error}</p> : null}
      {!jobs.length ? <p className="muted">Nothing in flight.</p> : null}
      <ul className="stack">
        {jobs.map((job) => (
          <li key={job.id} className="card">
            <strong>{job.title || job.nzo_id || job.id}</strong>
            <p className="muted">
              {job.status}
              {job.nzo_id ? ` · ${job.nzo_id}` : ""}
            </p>
            {job.status === "asked" ? (
              <button type="button" className="primary" onClick={() => api.confirmJob(job.id).then(reload)}>
                Queue to SAB
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
