/**
 * Maintain status dock helpers — living jobs only (idle chips collapse).
 */

/** True when a progress blob is actively running. */
export function livingJob(status, isRunning) {
  if (!status || typeof isRunning !== "function") return false;
  return Boolean(isRunning(status));
}
