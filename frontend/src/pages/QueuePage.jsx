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
  humanError,
  queueNeedsYouHelp,
} from "../copy.js";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import {
  DEFAULT_QUEUE_VIEW,
  bulkDismissConfirmCopy,
  dismissibleQueueJobs,
  emptyQueueViewCopy,
  normalizeQueueView,
  queueCounts,
  queueViewLabel,
} from "../queueDesk.js";

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
  const [counts, setCounts] = useState(queueCounts());
  const [view, setView] = useState(DEFAULT_QUEUE_VIEW);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingSab, setPendingSab] = useState(null);
  const [pendingBulk, setPendingBulk] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  useDocumentTitle(PAGE_TITLE_DOWNLOADS);

  function reload(nextView = view) {
    const key = normalizeQueueView(nextView);
    setLoading(true);
    api
      .queue({ view: key })
      .then((data) => {
        setJobs(data.jobs || []);
        setCounts(queueCounts(data.counts));
        setView(normalizeQueueView(data.view || key));
        setError("");
        setLoading(false);
      })
      .catch((err) => {
        setError(humanError(err));
        setLoading(false);
      });
  }

  useEffect(() => {
    reload(DEFAULT_QUEUE_VIEW);
    // Default Downloads open on Needs decision (PRD-011).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function chooseView(next) {
    const key = normalizeQueueView(next);
    if (key === view) return;
    setView(key);
    reload(key);
  }

  async function runBulkDismiss(targets) {
    if (!targets?.length || bulkBusy) return;
    setBulkBusy(true);
    setError("");
    try {
      for (const job of targets) {
        await api.dismissJob(job.id);
      }
      setPendingBulk(null);
      reload(view);
    } catch (err) {
      setError(humanError(err));
      reload(view);
    } finally {
      setBulkBusy(false);
    }
  }

  const listed = sortQueueNeedsYouFirst(jobs);
  const hasNeedsYou = listed.some((job) => job.status === "review");
  const dismissible = dismissibleQueueJobs(listed);
  const bulkCopy = bulkDismissConfirmCopy(dismissible);
  const emptyCopy = emptyQueueViewCopy(view);

  return (
    <div className="admin-room page-settle queue-page" data-density="compact">
      <p className="kicker">Downloads</p>
      <h1>Downloads</h1>
      <p className="lede">Asked slips, SAB jobs, and volumes being filed. Living chips live on Find cards.</p>
      <div className="chip-row" role="group" aria-label="Downloads view" data-testid="queue-view-filters">
        {["actionable", "active", "history", "all"].map((key) => {
          const n = counts[key] ?? 0;
          const label = queueViewLabel(key);
          return (
            <button
              key={key}
              type="button"
              className="chip"
              aria-pressed={view === key}
              onClick={() => chooseView(key)}
              data-testid={`queue-view-${key}`}
            >
              {label}
              {n > 0 ? ` (${n})` : ""}
            </button>
          );
        })}
      </div>
      {dismissible.length > 0 ? (
        <div className="cta-row compact">
          <button
            type="button"
            className="cta outline compact"
            onClick={() => setPendingBulk(dismissible)}
            disabled={bulkBusy}
            data-testid="queue-bulk-dismiss"
          >
            Dismiss {dismissible.length} terminal
          </button>
        </div>
      ) : null}
      {hasNeedsYou ? <p className="empty-note" data-testid="queue-needs-you-help">{queueNeedsYouHelp()}</p> : null}
      {error ? <Alert>{error}</Alert> : null}
      {loading ? (
        <WarmLoad message="Warming the lamp on Downloads…" testId="queue-loading" />
      ) : null}
      {!loading && !jobs.length ? (
        <p className="empty-note" data-testid="queue-empty">
          {emptyCopy}
        </p>
      ) : null}
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
              const canDismissArrived = job.status === "organized";
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
                      <button type="button" className="cta" onClick={() => setPendingSab(job)}>
                        Queue to SAB
                      </button>
                      <button
                        type="button"
                        className="cta outline"
                        onClick={() =>
                          api
                            .dismissJob(job.id)
                            .then(() => reload(view))
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
                            .then(() => reload(view))
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
                            .then(() => reload(view))
                            .catch((err) => setError(humanError(err)))
                        }
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                  {canDismissArrived ? (
                    <div className="cta-row">
                      <button
                        type="button"
                        className="cta outline"
                        onClick={() =>
                          api
                            .dismissJob(job.id)
                            .then(() => reload(view))
                            .catch((err) => setError(humanError(err)))
                        }
                        data-testid="queue-dismiss-arrived"
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
            .then(() => reload(view))
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
      <ConfirmDialog
        open={Boolean(pendingBulk?.length)}
        title={bulkCopy.title}
        confirmLabel={bulkCopy.confirmLabel}
        busy={bulkBusy}
        onConfirm={() => runBulkDismiss(pendingBulk)}
        onCancel={() => setPendingBulk(null)}
        testId="queue-bulk-dismiss-dialog"
        confirmTestId="queue-bulk-dismiss-confirm"
      >
        <p data-testid="queue-bulk-dismiss-count">{bulkCopy.body}</p>
        <p className="muted" data-testid="queue-bulk-dismiss-undo">
          {bulkCopy.undoReminder}
        </p>
      </ConfirmDialog>
    </div>
  );
}
