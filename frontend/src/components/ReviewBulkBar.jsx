import { memo } from "react";

/**
 * Desk tally is its own line, with one text node per count.
 * Polls must not remount it or rewrite a count that did not change —
 * a shared flex row of conditional paragraphs was swapping those nodes.
 */
const DeskTally = memo(function DeskTally({ trusted, ambiguous, failed }) {
  const ready = Number(trusted) || 0;
  const need = Number(ambiguous) || 0;
  const unavailable = Number(failed) || 0;
  if (ready + need + unavailable <= 0) return null;
  return (
    <p className="muted review-desk-tally" data-testid="review-triage-counts" role="status">
      {"On the desk: "}<span>{ready}</span>{" ready to file · "}<span>{need}</span>{" need a decision · "}<span>{unavailable}</span>{" model unavailable"}
    </p>
  );
});

/** Sorting bulk bar: unpack repair/retry, clear extra-files, purge, and model triage. */
export default function ReviewBulkBar({
  show,
  unpackCount,
  onRepair,
  onRetry,
  showBulkClear,
  extraFilesClearing,
  extraFilesBacklog,
  extraFilesCount,
  onClearExtraFiles,
  showBulkPurge,
  purgeRunning,
  reviewBacklog,
  slipCount,
  onPurgeDuplicates,
  lowConfidenceCount,
  triageRunning,
  triageProgress,
  onStartTriage,
  trustedCount,
  applyingTrusted,
  onApplyTrusted,
  triageLine,
  triageCounts,
  modelNote,
  bulkNote,
  showExtraFilesProgress,
  showPurgeProgress,
}) {
  if (!show) return null;
  const counts = triageCounts || {};

  return (
    <div className="review-bulk" data-testid="review-bulk">
      <div className="cta-row" role="group" aria-label="Sorting actions">
        {unpackCount ? (
          <>
            <button type="button" className="cta outline compact" onClick={() => onRepair()}>
              Repair unpack slips
            </button>
            <button type="button" className="cta outline compact" onClick={() => onRetry()}>
              Retry unpack slips
            </button>
          </>
        ) : null}
        {showBulkClear ? (
          <button
            type="button"
            className="cta compact"
            onClick={() => onClearExtraFiles()}
            disabled={extraFilesClearing}
            data-testid="review-bulk-extra-files"
          >
            {extraFilesClearing
              ? "Clearing…"
              : extraFilesBacklog > 0 && extraFilesCount === 0
                ? `Clear extra-files slips (${extraFilesBacklog})`
                : "Clear extra-files slips"}
          </button>
        ) : null}
        {showBulkPurge ? (
          <button
            type="button"
            className="cta outline compact"
            onClick={() => onPurgeDuplicates()}
            disabled={purgeRunning}
            data-testid="review-bulk-purge-duplicates"
            title="Dismiss slips whose content is already on the shelf, or exact duplicate slips of each other (keeps one)."
          >
            {purgeRunning
              ? "Purging…"
              : reviewBacklog > slipCount
                ? `Purge duplicates (${reviewBacklog})`
                : "Purge duplicates"}
          </button>
        ) : null}
        {lowConfidenceCount || triageRunning ? (
          <button type="button" className="cta outline compact" onClick={() => onStartTriage()} disabled={triageRunning}>
            {triageRunning
              ? `Checking slips (${Number(triageProgress?.done || 0)}/${Number(triageProgress?.total || 0)})…`
              : `Check low-confidence slips (${lowConfidenceCount})`}
          </button>
        ) : null}
        {trustedCount ? (
          <button type="button" className="cta compact" onClick={() => onApplyTrusted()} disabled={applyingTrusted}>
            {applyingTrusted ? "Filing trusted matches…" : `Apply trusted matches (${trustedCount})`}
          </button>
        ) : null}
      </div>
      <DeskTally trusted={counts.trusted} ambiguous={counts.ambiguous} failed={counts.failed} />
      {triageLine ? (
        <p key="model-triage" className="muted" role="status" data-testid="review-model-triage">
          {triageLine}
        </p>
      ) : null}
      {modelNote ? (
        <p key="model-note" className="muted" role="status">
          {modelNote}
        </p>
      ) : null}
      {bulkNote && !showExtraFilesProgress && !showPurgeProgress ? (
        <p key="bulk-note" className="muted" role="status">
          {bulkNote}
        </p>
      ) : null}
    </div>
  );
}
