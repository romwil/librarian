import { useEffect, useRef, useState } from "react";
import { nextProgressPollWait } from "../lib/maintainDock.js";

/**
 * Poll a progress status endpoint while active (and optionally while idle).
 * Hidden tabs pause scheduling (P2-HIGH-02) — visibilitychange resumes.
 * With `probe: true` and `pollIdle: false`, runs one fetch (plus wake/visibility)
 * and only keeps polling while a job is running (P2-MED-05).
 *
 * @param {object} opts
 * @param {() => Promise<object|null>} opts.fetchStatus
 * @param {(status: object|null) => boolean} opts.isRunning
 * @param {boolean} [opts.active] When true, poll at liveMs after each tick.
 * @param {boolean} [opts.pollIdle] When true and not active, keep a slow poll.
 * @param {boolean} [opts.probe] When true, run at least one poll even if idle.
 * @param {string} [opts.wakeEvent] window event name that triggers a probe.
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
  probe = false,
  wakeEvent = "",
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
    if (!active && !pollIdle && !probe) return undefined;
    let cancelled = false;
    let timer = 0;

    function pageHidden() {
      return typeof document !== "undefined" && document.visibilityState === "hidden";
    }

    function schedule(wait) {
      window.clearTimeout(timer);
      if (cancelled || pageHidden() || wait == null) return;
      timer = window.setTimeout(poll, wait);
    }

    async function poll() {
      if (cancelled || pageHidden()) return;
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
        const wait = nextProgressPollWait({
          live,
          active,
          pollIdle,
          liveMs,
          idleMs,
        });
        schedule(wait);
      } catch {
        const wait = nextProgressPollWait({
          live: false,
          active,
          pollIdle,
          liveMs,
          idleMs,
        });
        schedule(wait);
      }
    }

    function onVisibility() {
      if (cancelled) return;
      if (pageHidden()) {
        window.clearTimeout(timer);
        return;
      }
      poll();
    }

    function onWake() {
      if (cancelled || pageHidden()) return;
      poll();
    }

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }
    if (wakeEvent && typeof window !== "undefined") {
      window.addEventListener(wakeEvent, onWake);
    }
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
      if (wakeEvent && typeof window !== "undefined") {
        window.removeEventListener(wakeEvent, onWake);
      }
    };
  }, [fetchStatus, isRunning, active, pollIdle, probe, wakeEvent, liveMs, idleMs]);

  return { status, setStatus, running, setRunning };
}

export default useProgressJob;
