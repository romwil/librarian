import { useEffect, useState } from "react";
import { api } from "../api.js";
import { jobHouseholdLabel, jobQueueDetail } from "../cover.js";
import { emptyQueueCopy, humanError } from "../copy.js";

export default function QueuePage() {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");

  function reload() {
    api
      .queue()
      .then((data) => setJobs(data.jobs || []))
      .catch((err) => setError(humanError(err)));
  }

  useEffect(reload, []);

  return (
    <div className="admin-room">
      <p className="kicker">Exceptions</p>
      <h1>Queue</h1>
      <p className="lede">Living chips live on Find cards. This list is for asked slips, SAB jobs, and volumes being filed.</p>
      {error ? <p className="alert">{error}</p> : null}
      {!jobs.length ? <p className="empty-note">{emptyQueueCopy()}</p> : null}
      <ul className="stack">
        {jobs.map((job) => {
          const household = jobHouseholdLabel(job.status) || job.status;
          const raw = jobQueueDetail(job);
          return (
            <li key={job.id} className="card">
              <strong>{job.title || job.nzo_id || job.id}</strong>
              <p data-testid="queue-household">{household}</p>
              {raw ? <p className="muted">{raw}</p> : null}
              {job.status === "asked" ? (
                <button
                  type="button"
                  className="cta"
                  onClick={() =>
                    api
                      .confirmJob(job.id)
                      .then(reload)
                      .catch((err) => setError(humanError(err)))
                  }
                >
                  Queue to SAB
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
