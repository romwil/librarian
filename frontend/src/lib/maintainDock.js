/**
 * Maintain status dock helpers — living jobs only (idle chips collapse).
 * P2-MED-05: wake the multiplex probe when a Maintain action starts a job.
 */

import {
  enrichIsRunning,
  scanIsRunning,
} from "../actionBusy.js";
import { ingestIsRunning } from "../ingest.js";
import { extraFilesReprocessIsRunning } from "../review.js";

/** CustomEvent name — dock listens so it can probe without idle four-poll. */
export const MAINTAIN_JOBS_WAKE = "librarian:maintain-jobs-wake";

/** True when a progress blob is actively running. */
export function livingJob(status, isRunning) {
  if (!status || typeof isRunning !== "function") return false;
  return Boolean(isRunning(status));
}

/** True when any multiplexed Maintain job blob is live. */
export function anyMaintainJobRunning(bundle) {
  if (!bundle || typeof bundle !== "object") return false;
  return (
    scanIsRunning(bundle.scan) ||
    enrichIsRunning(bundle.enrich) ||
    ingestIsRunning(bundle.ingest) ||
    extraFilesReprocessIsRunning(bundle.extra_files)
  );
}

/** Ask MaintainStatusDock to probe jobs/status once (no idle cadence). */
export function wakeMaintainJobs() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(MAINTAIN_JOBS_WAKE));
}

/**
 * Decide the next poll delay for useProgressJob.
 * @returns {number|null} ms to wait, or null to stop polling.
 */
export function nextProgressPollWait({ live, active, pollIdle, liveMs, idleMs }) {
  if (live || active) return liveMs;
  if (pollIdle) return idleMs;
  return null;
}
