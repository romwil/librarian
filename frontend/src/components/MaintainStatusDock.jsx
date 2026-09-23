import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import {
  busyLabel,
  enrichIsRunning,
  enrichPhaseLabel,
  enrichProgressSummary,
  scanIsRunning,
  scanPhaseLabel,
  scanProgressSummary,
} from "../actionBusy.js";
import { ingestDisplayPath, ingestIsRunning, ingestPhaseLabel, ingestProgressPercent, ingestProgressSummary, ingestTallyLines } from "../ingest.js";
import {
  extraFilesReprocessIsRunning,
  extraFilesReprocessProgressPercent,
  extraFilesReprocessProgressSummary,
} from "../review.js";

/**
 * Standardized job-status dock for Maintain — same shelf-progress / ingest-progress
 * pattern used on Settings scan/enrich and Review Clear extra-files.
 */
export default function MaintainStatusDock() {
  const [scanStatus, setScanStatus] = useState(null);
  const [enrichStatus, setEnrichStatus] = useState(null);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [extraStatus, setExtraStatus] = useState(null);
  const pollRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const [scan, enrich, ingest, extra] = await Promise.all([
          api.scanStatus().catch(() => null),
          api.enrichStatus().catch(() => null),
          api.ingestStatus().catch(() => null),
          api.reviewReprocessExtraFilesStatus().catch(() => null),
        ]);
        if (cancelled) return;
        if (scan) setScanStatus(scan);
        if (enrich) setEnrichStatus(enrich);
        if (ingest) setIngestStatus(ingest);
        if (extra) setExtraStatus(extra);
        const live =
          scanIsRunning(scan) ||
          enrichIsRunning(enrich) ||
          ingestIsRunning(ingest) ||
          extraFilesReprocessIsRunning(extra);
        pollRef.current = window.setTimeout(poll, live ? 700 : 4000);
      } catch {
        if (!cancelled) pollRef.current = window.setTimeout(poll, 5000);
      }
    }

    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(pollRef.current);
    };
  }, []);

  const cards = [];

  if (scanStatus && (scanIsRunning(scanStatus) || scanStatus.status === "completed" || scanStatus.status === "failed")) {
    cards.push(
      <section key="scan" className="shelf-progress" data-testid="maintain-scan-status" aria-live="polite">
        <p className="kicker">Scan</p>
        <p className="muted">
          {scanPhaseLabel(scanStatus.phase)}
          {scanStatus.total ? ` · ${scanStatus.done || 0} of ${scanStatus.total}` : ""}
        </p>
        <p className="muted" role="status">
          {scanProgressSummary(scanStatus) || busyLabel("scan")}
        </p>
      </section>,
    );
  }

  if (
    enrichStatus &&
    (enrichIsRunning(enrichStatus) || enrichStatus.status === "completed" || enrichStatus.status === "failed")
  ) {
    cards.push(
      <section key="enrich" className="shelf-progress" data-testid="maintain-enrich-status" aria-live="polite">
        <p className="kicker">Enrich</p>
        <p className="muted">
          {enrichPhaseLabel(enrichStatus.phase)}
          {enrichStatus.total ? ` · ${enrichStatus.done || 0} of ${enrichStatus.total}` : ""}
        </p>
        <p className="muted" role="status">
          {enrichProgressSummary(enrichStatus) || busyLabel("enrich")}
        </p>
      </section>,
    );
  }

  if (
    ingestStatus &&
    (ingestIsRunning(ingestStatus) || ingestStatus.status === "completed" || ingestStatus.status === "failed")
  ) {
    const percent = ingestProgressPercent(ingestStatus);
    const tallyLines = ingestTallyLines(ingestStatus);
    const displayPath = ingestDisplayPath(ingestStatus.current_path || ingestStatus.source_path || "");
    cards.push(
      <section key="ingest" className="ingest-progress" data-testid="maintain-ingest-status" aria-live="polite">
        <p className="kicker">Shelving</p>
        <p className="muted">
          {ingestPhaseLabel(ingestStatus.phase)}
          {ingestStatus.total
            ? ` · ${ingestStatus.done || 0} of ${ingestStatus.total}`
            : ingestStatus.volumes_found
              ? ` · found ${ingestStatus.volumes_found} volumes`
              : ""}
          {ingestStatus.files_found && ingestStatus.phase === "scanning"
            ? ` · ${ingestStatus.files_found} files`
            : ""}
          {percent != null ? ` · ${percent}%` : ""}
        </p>
        {percent != null ? (
          <div
            className="ingest-progress-meter"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label="Shelving progress"
          >
            <span className="ingest-progress-meter-fill" style={{ width: `${percent}%` }} />
          </div>
        ) : ingestStatus.phase === "scanning" ? (
          <div className="ingest-progress-meter ingest-progress-meter--indeterminate" aria-hidden="true">
            <span className="ingest-progress-meter-fill" />
          </div>
        ) : null}
        {ingestStatus.current_title ? (
          <p className="lede ingest-progress-title">{ingestStatus.current_title}</p>
        ) : null}
        {displayPath ? (
          <p className="muted ingest-progress-path" title={ingestStatus.current_path || ""}>
            {displayPath}
          </p>
        ) : null}
        {tallyLines.length ? (
          <ul className="ingest-progress-tallies">
            {tallyLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
        <p className="muted" role="status">
          {ingestProgressSummary(ingestStatus) || "Adding…"}
        </p>
      </section>,
    );
  }

  if (
    extraStatus &&
    (extraFilesReprocessIsRunning(extraStatus) ||
      extraStatus.status === "completed" ||
      extraStatus.status === "failed")
  ) {
    const percent = extraFilesReprocessProgressPercent(extraStatus);
    cards.push(
      <section
        key="extra"
        className="ingest-progress review-extra-files-progress"
        data-testid="maintain-extra-files-status"
        aria-live="polite"
      >
        <p className="kicker">Clear extra-files</p>
        <p className="muted">
          {extraStatus.phase || "clearing"}
          {extraStatus.total ? ` · ${extraStatus.done || 0} of ${extraStatus.total}` : ""}
          {percent != null ? ` · ${percent}%` : ""}
        </p>
        {percent != null ? (
          <div
            className="ingest-progress-meter"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label="Clear extra-files progress"
          >
            <span className="ingest-progress-meter-fill" style={{ width: `${percent}%` }} />
          </div>
        ) : null}
        <p className="muted" role="status">
          {extraFilesReprocessProgressSummary(extraStatus) || "Clearing…"}
        </p>
      </section>,
    );
  }

  if (!cards.length) {
    return (
      <section className="maintain-status-idle" data-testid="maintain-status-idle">
        <p className="kicker">Telemetry</p>
        <p className="muted">No scan, enrich, shelving, or clear jobs running.</p>
      </section>
    );
  }

  return (
    <div className="maintain-status-dock" data-testid="maintain-status-dock">
      <p className="kicker">Telemetry</p>
      <div className="maintain-status-grid">{cards}</div>
    </div>
  );
}
