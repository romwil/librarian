import { useCallback } from "react";
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
import {
  ingestDisplayPath,
  ingestIsRunning,
  ingestPhaseLabel,
  ingestProgressPercent,
  ingestProgressSummary,
  ingestTallyLines,
} from "../ingest.js";
import {
  extraFilesReprocessIsRunning,
  extraFilesReprocessProgressPercent,
  extraFilesReprocessProgressSummary,
} from "../review.js";
import { useProgressJob } from "../hooks/useProgressJob.js";
import JobProgress from "./JobProgress.jsx";

function jobVisible(status, isRunning) {
  if (!status) return false;
  return isRunning(status) || status.status === "completed" || status.status === "failed";
}

/**
 * Standardized job-status dock for Maintain — one live telemetry surface for
 * scan / enrich / shelving / clear. Embedded Add-to-library progress is hidden
 * on Maintain so this dock is the only status UI.
 */
export default function MaintainStatusDock() {
  const fetchScan = useCallback(() => api.scanStatus().catch(() => null), []);
  const fetchEnrich = useCallback(() => api.enrichStatus().catch(() => null), []);
  const fetchIngest = useCallback(() => api.ingestStatus().catch(() => null), []);
  const fetchExtra = useCallback(() => api.reviewReprocessExtraFilesStatus().catch(() => null), []);

  const { status: scanStatus } = useProgressJob({
    fetchStatus: fetchScan,
    isRunning: scanIsRunning,
    pollIdle: true,
  });
  const { status: enrichStatus } = useProgressJob({
    fetchStatus: fetchEnrich,
    isRunning: enrichIsRunning,
    pollIdle: true,
  });
  const { status: ingestStatus } = useProgressJob({
    fetchStatus: fetchIngest,
    isRunning: ingestIsRunning,
    pollIdle: true,
  });
  const { status: extraStatus } = useProgressJob({
    fetchStatus: fetchExtra,
    isRunning: extraFilesReprocessIsRunning,
    pollIdle: true,
  });

  const cards = [];

  if (jobVisible(scanStatus, scanIsRunning)) {
    cards.push(
      <JobProgress
        key="scan"
        className="shelf-progress"
        testId="maintain-scan-status"
        kicker="Scan"
        phaseLabel={scanPhaseLabel(scanStatus.phase)}
        done={scanStatus.total ? scanStatus.done || 0 : 0}
        total={scanStatus.total || 0}
        statusLine={scanProgressSummary(scanStatus) || busyLabel("scan")}
      />,
    );
  }

  if (jobVisible(enrichStatus, enrichIsRunning)) {
    cards.push(
      <JobProgress
        key="enrich"
        className="shelf-progress"
        testId="maintain-enrich-status"
        kicker="Enrich"
        phaseLabel={enrichPhaseLabel(enrichStatus.phase)}
        done={enrichStatus.total ? enrichStatus.done || 0 : 0}
        total={enrichStatus.total || 0}
        statusLine={enrichProgressSummary(enrichStatus) || busyLabel("enrich")}
      />,
    );
  }

  if (jobVisible(ingestStatus, ingestIsRunning)) {
    const percent = ingestProgressPercent(ingestStatus);
    const tallyLines = ingestTallyLines(ingestStatus);
    const displayPath = ingestDisplayPath(ingestStatus.current_path || ingestStatus.source_path || "");
    const phaseExtra =
      !ingestStatus.total && ingestStatus.volumes_found
        ? ` · found ${ingestStatus.volumes_found} volumes`
        : "";
    const filesExtra =
      ingestStatus.files_found && ingestStatus.phase === "scanning"
        ? ` · ${ingestStatus.files_found} files`
        : "";
    cards.push(
      <JobProgress
        key="ingest"
        className="ingest-progress"
        testId="maintain-ingest-status"
        kicker="Shelving"
        phaseLabel={`${ingestPhaseLabel(ingestStatus.phase)}${phaseExtra}${filesExtra}`}
        done={ingestStatus.done || 0}
        total={ingestStatus.total || 0}
        percent={percent}
        indeterminate={percent == null && ingestStatus.phase === "scanning"}
        title={ingestStatus.current_title || ""}
        path={displayPath}
        pathTitle={ingestStatus.current_path || ""}
        tallies={tallyLines}
        statusLine={ingestProgressSummary(ingestStatus) || "Adding…"}
        meterLabel="Shelving progress"
      />,
    );
  }

  if (jobVisible(extraStatus, extraFilesReprocessIsRunning)) {
    const percent = extraFilesReprocessProgressPercent(extraStatus);
    cards.push(
      <JobProgress
        key="extra"
        className="ingest-progress review-extra-files-progress"
        testId="maintain-extra-files-status"
        kicker="Clear extra-files"
        phaseLabel={extraStatus.phase || "clearing"}
        done={extraStatus.done || 0}
        total={extraStatus.total || 0}
        percent={percent}
        statusLine={extraFilesReprocessProgressSummary(extraStatus) || "Clearing…"}
        meterLabel="Clear extra-files progress"
      />,
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
