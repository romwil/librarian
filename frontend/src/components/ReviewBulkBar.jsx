/** Holds desk bulk bar: unpack repair/retry, clear extra-files, purge, and model triage. */
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
  const deskTally =
    counts.trusted || counts.ambiguous || counts.failed
      ? `On the desk: ${counts.trusted} ready to file · ${counts.ambiguous} need a decision · ` +
        `${counts.failed} model unavailable`
      : "";

  return (
    <div className="cta-row review-bulk" data-testid="review-bulk">
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
      {triageLine ? (
        <p className="muted" role="status" data-testid="review-model-triage">
          {triageLine}
        </p>
      ) : null}
      {deskTally ? (
        <p className="muted" data-testid="review-triage-counts">
          {deskTally}
        </p>
      ) : null}
      {modelNote ? (
        <p className="muted" role="status">
          {modelNote}
        </p>
      ) : null}
      {bulkNote && !showExtraFilesProgress && !showPurgeProgress ? (
        <p className="muted" role="status">
          {bulkNote}
        </p>
      ) : null}
    </div>
  );
}
