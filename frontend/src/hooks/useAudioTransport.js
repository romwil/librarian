import { useCallback, useRef } from "react";

const EVENTS = {
  timeupdate: "onTimeUpdate",
  play: "onPlay",
  pause: "onPause",
  ended: "onEnded",
  error: "onError",
};

/**
 * One HTML5 <audio> transport for the whole app. The album player (music
 * queue) and the Listening room (audiobook bookmark, chapters, sleep) each own
 * a transport and layer their own queue on top — the queues never mix.
 *
 * Attach `audioRef` as the `ref` of a single <audio>. Handlers are read fresh on
 * every event, so callers may close over current state:
 * `onTimeUpdate`, `onPlay`, `onPause`, `onEnded`, `onError` get `(audio, event)`;
 * `onPlayRejected` gets the rejection from `audio.play()`.
 */
export function useAudioTransport(handlers = {}) {
  const elementRef = useRef(null);
  const unbindRef = useRef(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  // Callback ref: listeners bind in the same commit the <audio> mounts — the
  // album player's element only appears once the work payload has loaded.
  const audioRef = useCallback((node) => {
    unbindRef.current?.();
    unbindRef.current = null;
    elementRef.current = node;
    if (!node) return;
    const bound = Object.entries(EVENTS).map(([type, key]) => {
      const listener = (event) => handlersRef.current[key]?.(node, event);
      node.addEventListener(type, listener);
      return () => node.removeEventListener(type, listener);
    });
    unbindRef.current = () => bound.forEach((unbind) => unbind());
  }, []);

  const getAudio = useCallback(() => elementRef.current, []);

  const play = useCallback(() => {
    const audio = elementRef.current;
    if (!audio) return;
    const attempt = audio.play();
    if (attempt && typeof attempt.catch === "function") {
      attempt.catch((err) => handlersRef.current.onPlayRejected?.(err));
    }
  }, []);

  const pause = useCallback(() => {
    elementRef.current?.pause();
  }, []);

  const toggle = useCallback(() => {
    const audio = elementRef.current;
    if (!audio) return;
    if (audio.paused) play();
    else audio.pause();
  }, [play]);

  /** Stop and drop the source so the browser releases the stream. */
  const silence = useCallback(() => {
    const audio = elementRef.current;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    try {
      audio.load();
    } catch {
      /* ignore */
    }
  }, []);

  /**
   * Point the transport at `src`. Without `onReady` it plays at once; with it,
   * the source loads and `onReady(audio)` runs on `loadedmetadata` (the caller
   * seeks / plays from there). Returns false when there is nothing to play.
   */
  const start = useCallback(
    (src, { rate, onReady } = {}) => {
      const audio = elementRef.current;
      if (!audio || !src) return false;
      audio.src = src;
      if (rate) audio.playbackRate = rate;
      if (!onReady) {
        play();
        return true;
      }
      const onMeta = () => {
        audio.removeEventListener("loadedmetadata", onMeta);
        onReady(audio);
      };
      audio.addEventListener("loadedmetadata", onMeta);
      audio.load();
      return true;
    },
    [play],
  );

  const seek = useCallback((seconds) => {
    const audio = elementRef.current;
    if (!audio || !Number.isFinite(seconds)) return null;
    audio.currentTime = Math.max(0, seconds);
    return audio.currentTime;
  }, []);

  const setRate = useCallback((rate) => {
    if (elementRef.current) elementRef.current.playbackRate = rate;
  }, []);

  return { audioRef, getAudio, play, pause, toggle, silence, start, seek, setRate };
}
