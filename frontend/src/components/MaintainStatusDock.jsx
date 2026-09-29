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
import {
  MAINTAIN_JOBS_WAKE,
  anyMaintainJobRunning,
  livingJob,
} from "../lib/maintainDock.js";
import JobProgress from "./JobProgress.jsx";

/**
 * Standardized job-status dock for Maintain — one live telemetry surface for
 * scan / enrich / shelving / clear. Collapses entirely when nothing is running.
 * P2-MED-05: multiplexed `/api/maintain/jobs/status`; probe on mount / wake /
 * visibility — no idle four-poll while collapsed.
 */
export default function MaintainStatusDock() {
  const fetchJobs = useCallback(() => api.maintainJobsStatus().catch(() => null), []);

  const { status: jobs } = useProgressJob({
    fetchStatus: fetchJobs,
    isRunning: anyMaintainJobRunning,
    pollIdle: false,
    probe: true,
    wakeEvent: MAINTAIN_JOBS_WAKE,
    liveMs: 700,
  });

  const scanStatus = jobs?.scan ?? null;
  const enrichStatus = jobs?.enrich ?? null;
  const ingestStatus = jobs?.ingest ?? null;
  const extraStatus = jobs?.extra_files ?? null;

  const cards = [];

  if (livingJob(scanStatus, scanIsRunning)) {
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

  if (livingJob(enrichStatus, enrichIsRunning)) {
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

  if (livingJob(ingestStatus, ingestIsRunning)) {
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

  if (livingJob(extraStatus, extraFilesReprocessIsRunning)) {
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

  if (!cards.length) return null;

  return (
    <div className="maintain-status-dock" data-testid="maintain-status-dock">
      <p className="kicker">Telemetry</p>
      <div className="maintain-status-grid">{cards}</div>
    </div>
  );
}
