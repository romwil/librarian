import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import Alert from "../components/Alert.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import WarmLoad from "../components/WarmLoad.jsx";
import { jobChipTone, jobHouseholdLabel, jobNeedsYouReason, sortQueueNeedsYouFirst } from "../cover.js";
import {
  PAGE_TITLE_DOWNLOADS,
  QUEUE_SAB_BODY,
  QUEUE_SAB_TITLE,
  emptyQueueCopy,
  humanError,
  queueNeedsYouHelp,
} from "../copy.js";
import useDocumentTitle from "../hooks/useDocumentTitle.js";

function isUnpackStuck(job) {
  const reason = String(job?.review_reason || "").trim();
  const problem = String(job?.folder_diagnosis?.problem || job?.payload?.problem || "").trim();
  return reason === "unpack_stuck" || problem === "unpack_stuck";
}

function jobPath(job) {
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  return String(job.storage_path || payload.path || "").trim();
}

export default function QueuePage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingSab, setPendingSab] = useState(null);
  useDocumentTitle(PAGE_TITLE_DOWNLOADS);

  function reload() {
    setLoading(true);
    api
      .queue()
      .then((data) => {
        setJobs(data.jobs || []);
        setError("");
        setLoading(false);
      })
      .catch((err) => {
        setError(humanError(err));
        setLoading(false);
      });
  }

  useEffect(reload, []);

  const listed = sortQueueNeedsYouFirst(jobs);
  const hasNeedsYou = listed.some((job) => job.status === "review");

  return (
    <div className="admin-room page-settle queue-page" data-density="compact">
      <p className="kicker">Downloads</p>
      <h1>Downloads</h1>
      <p className="lede">Asked slips, SAB jobs, and volumes being filed. Living chips live on Find cards.</p>
      {hasNeedsYou ? <p className="empty-note" data-testid="queue-needs-you-help">{queueNeedsYouHelp()}</p> : null}
      {error ? <Alert>{error}</Alert> : null}
      {loading ? (
        <WarmLoad message="Warming the lamp on Downloads…" testId="queue-loading" />
      ) : null}
      {!loading && !jobs.length ? <p className="empty-note">{emptyQueueCopy()}</p> : null}
      <ul className="stack">
        {!loading
          ? listed.map((job) => {
              const household = jobHouseholdLabel(job.status) || job.status;
              const tone = jobChipTone(job.status);
              const needsYou = jobNeedsYouReason(job);
              const path = jobPath(job);
              const nzo = String(job.nzo_id || "").trim();
              const fail = String(job.error || "").trim();
              const reviewTo = job.work_id ? `/review?work=${encodeURIComponent(job.work_id)}` : "/review";
              const unpack = isUnpackStuck(job);
              const actionableFail = job.status === "failed" || job.status === "skipped";
              return (
                <li key={job.id} className="card queue-job" data-testid="queue-job" data-status={job.status || ""}>
                  <strong className="queue-job-title">{job.title || job.nzo_id || job.id}</strong>
                  <p className="chip-row" data-testid="queue-household">
                    <span className={["live-chip", tone].filter(Boolean).join(" ")}>{household}</span>
                    {unpack ? (
                      <Link className="live-chip is-review" to={reviewTo} data-testid="queue-unpack-badge">
                        Unpack stuck
                      </Link>
                    ) : null}
                  </p>
                  {needsYou ? <p data-testid="queue-needs-you-reason">{needsYou}</p> : null}
                  {fail && job.status === "failed" ? <p data-testid="queue-fail-message">{fail}</p> : null}
                  {path || nzo ? (
                    <details className="queue-job-details">
                      <summary>Details</summary>
                      {path ? <p className="muted" data-testid="queue-ops-detail">{path}</p> : null}
                      {nzo ? <p className="muted">{nzo}</p> : null}
                    </details>
                  ) : null}
                  {job.status === "review" ? (
                    <div className="cta-row">
                      <Link className="cta" to={reviewTo} data-testid="queue-open-review">
                        Open Sorting
                      </Link>
                    </div>
                  ) : null}
                  {job.status === "asked" ? (
                    <div className="cta-row">
                      <button
                        type="button"
                        className="cta"
                        onClick={() => setPendingSab(job)}
                      >
                        Queue to SAB
                      </button>
                      <button
                        type="button"
                        className="cta outline"
                        onClick={() =>
                          api
                            .dismissJob(job.id)
                            .then(reload)
                            .catch((err) => setError(humanError(err)))
                        }
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                  {actionableFail ? (
                    <div className="cta-row">
                      <button
                        type="button"
                        className="cta"
                        onClick={() =>
                          api
                            .retryJob(job.id)
                            .then(reload)
                            .catch((err) => setError(humanError(err)))
                        }
                      >
                        Try again
                      </button>
                      <button
                        type="button"
                        className="cta outline"
                        onClick={() =>
                          api
                            .dismissJob(job.id)
                            .then(reload)
                            .catch((err) => setError(humanError(err)))
                        }
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })
          : null}
      </ul>
      <ConfirmDialog
        open={Boolean(pendingSab)}
        title={QUEUE_SAB_TITLE}
        confirmLabel="Queue to SAB"
        onConfirm={() => {
          const job = pendingSab;
          setPendingSab(null);
          if (!job?.id) return;
          api
            .confirmJob(job.id)
            .then(reload)
            .catch((err) => setError(humanError(err)));
        }}
        onCancel={() => setPendingSab(null)}
        testId="queue-sab-confirm"
      >
        <p>
          {pendingSab?.title ? `This starts a download for ${pendingSab.title}. ` : null}
          {QUEUE_SAB_BODY}
        </p>
      </ConfirmDialog>
    </div>
  );
}
