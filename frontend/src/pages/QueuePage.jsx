import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { jobChipTone, jobHouseholdLabel, jobNeedsYouReason, jobQueueDetail } from "../cover.js";
import { emptyQueueCopy, humanError, queueNeedsYouHelp } from "../copy.js";

function isUnpackStuck(job) {
  const reason = String(job?.review_reason || "").trim();
  const problem = String(job?.folder_diagnosis?.problem || job?.payload?.problem || "").trim();
  return reason === "unpack_stuck" || problem === "unpack_stuck";
}

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

  const hasNeedsYou = jobs.some((job) => job.status === "review");

  return (
    <div className="admin-room">
      <p className="kicker">Exceptions</p>
      <h1>Queue</h1>
      <p className="lede">Living chips live on Find cards. This list is for asked slips, SAB jobs, and volumes being filed.</p>
      {hasNeedsYou ? <p className="empty-note" data-testid="queue-needs-you-help">{queueNeedsYouHelp()}</p> : null}
      {error ? <p className="alert">{error}</p> : null}
      {!jobs.length ? <p className="empty-note">{emptyQueueCopy()}</p> : null}
      <ul className="stack">
        {jobs.map((job) => {
          const household = jobHouseholdLabel(job.status) || job.status;
          const tone = jobChipTone(job.status);
          const needsYou = jobNeedsYouReason(job);
          const raw = jobQueueDetail(job);
          const reviewTo = job.work_id ? `/review?work=${encodeURIComponent(job.work_id)}` : "/review";
          const unpack = isUnpackStuck(job);
          return (
            <li key={job.id} className="card" data-testid="queue-job" data-status={job.status || ""}>
              <strong>{job.title || job.nzo_id || job.id}</strong>
              <p className="chip-row" data-testid="queue-household">
                <span className={["live-chip", tone].filter(Boolean).join(" ")}>{household}</span>
                {unpack ? (
                  <Link className="live-chip is-review" to={reviewTo} data-testid="queue-unpack-badge">
                    Unpack stuck
                  </Link>
                ) : null}
              </p>
              {needsYou ? <p data-testid="queue-needs-you-reason">{needsYou}</p> : null}
              {raw ? <p className="muted" data-testid="queue-ops-detail">{raw}</p> : null}
              {job.status === "review" ? (
                <div className="cta-row">
                  <Link className="cta" to={reviewTo} data-testid="queue-open-review">
                    Open Review
                  </Link>
                </div>
              ) : null}
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
