import { useEffect, useRef, useState } from "react";

/**
 * Poll a progress status endpoint while active (and optionally while idle).
 *
 * @param {object} opts
 * @param {() => Promise<object|null>} opts.fetchStatus
 * @param {(status: object|null) => boolean} opts.isRunning
 * @param {boolean} [opts.active] When true, poll at liveMs after each tick.
 * @param {boolean} [opts.pollIdle] When true and not active, keep a slow poll.
 * @param {number} [opts.liveMs]
 * @param {number} [opts.idleMs]
 * @param {(status: object|null) => void} [opts.onUpdate]
 * @param {(status: object|null) => void} [opts.onSettled] Called once when a run leaves running.
 */
export function useProgressJob({
  fetchStatus,
  isRunning,
  active = false,
  pollIdle = false,
  liveMs = 700,
  idleMs = 4000,
  onUpdate,
  onSettled,
} = {}) {
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const onUpdateRef = useRef(onUpdate);
  const onSettledRef = useRef(onSettled);
  const wasRunningRef = useRef(false);
  onUpdateRef.current = onUpdate;
  onSettledRef.current = onSettled;

  useEffect(() => {
    if (!fetchStatus || typeof isRunning !== "function") return undefined;
    if (!active && !pollIdle) return undefined;
    let cancelled = false;
    let timer = 0;

    async function poll() {
      try {
        const next = await fetchStatus();
        if (cancelled) return;
        setStatus(next);
        const live = Boolean(isRunning(next));
        setRunning(live);
        onUpdateRef.current?.(next);
        if (wasRunningRef.current && !live) {
          onSettledRef.current?.(next);
        }
        wasRunningRef.current = live;
        const wait = live || active ? liveMs : idleMs;
        timer = window.setTimeout(poll, wait);
      } catch {
        if (!cancelled) timer = window.setTimeout(poll, idleMs);
      }
    }

    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [fetchStatus, isRunning, active, pollIdle, liveMs, idleMs]);

  return { status, setStatus, running, setRunning };
}

export default useProgressJob;
