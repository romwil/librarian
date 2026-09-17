import { useEffect, useRef, useState } from "react";
import {
  isAudioFile,
  playableTracks,
  playerAfterEnded,
  playerToggleAlbum,
  playerToggleTrack,
  workStreamUrl,
} from "../music.js";

function isOnDisk(row) {
  return row?.on_disk !== false;
}

/**
 * Shared HTML5 <audio> controller for a music work page.
 * Attach audioRef to a single <audio preload="none"> on the page.
 */
export function useAlbumPlayer({ workId, files = [], enabled = false }) {
  const audioRef = useRef(null);
  const [playingId, setPlayingId] = useState(null);
  const [mode, setMode] = useState(null);
  const playingIdRef = useRef(null);
  const modeRef = useRef(null);
  const tracksRef = useRef([]);
  const tracks = enabled ? playableTracks(files) : [];

  tracksRef.current = tracks;
  playingIdRef.current = playingId;
  modeRef.current = mode;

  function applyState(next) {
    setPlayingId(next.playingId);
    setMode(next.mode);
  }

  function silence() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    try {
      audio.load();
    } catch {
      /* ignore */
    }
  }

  function stop() {
    silence();
    applyState({ playingId: null, mode: null });
  }

  function loadAndPlay(fileId, nextMode) {
    const audio = audioRef.current;
    const id = String(fileId || "");
    const src = workStreamUrl(workId, id);
    if (!audio || !src) {
      stop();
      return;
    }
    audio.src = src;
    const playAttempt = audio.play();
    if (playAttempt && typeof playAttempt.catch === "function") {
      playAttempt.catch(() => stop());
    }
    applyState({ playingId: id, mode: nextMode });
  }

  function toggleTrack(fileId) {
    if (!enabled) return;
    const next = playerToggleTrack({ playingId, mode }, fileId);
    if (!next.playingId) {
      stop();
      return;
    }
    loadAndPlay(next.playingId, next.mode);
  }

  function toggleAlbum() {
    if (!enabled) return;
    const next = playerToggleAlbum({ playingId, mode }, tracks);
    if (!next.playingId) {
      stop();
      return;
    }
    loadAndPlay(next.playingId, next.mode);
  }

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    function onEnded() {
      const next = playerAfterEnded(
        { playingId: playingIdRef.current, mode: modeRef.current },
        tracksRef.current,
      );
      if (!next.playingId) {
        silence();
        applyState({ playingId: null, mode: null });
        return;
      }
      const src = workStreamUrl(workId, next.playingId);
      if (!src) {
        silence();
        applyState({ playingId: null, mode: null });
        return;
      }
      audio.src = src;
      const playAttempt = audio.play();
      if (playAttempt && typeof playAttempt.catch === "function") {
        playAttempt.catch(() => {
          silence();
          applyState({ playingId: null, mode: null });
        });
      }
      applyState(next);
    }

    audio.addEventListener("ended", onEnded);
    return () => audio.removeEventListener("ended", onEnded);
  }, [workId]);

  useEffect(() => {
    silence();
    applyState({ playingId: null, mode: null });
  }, [workId]);

  const nowPlaying = tracks.find((row) => String(row.id) === String(playingId || "")) || null;

  return {
    enabled: Boolean(enabled) && tracks.length > 0,
    tracks,
    playingId,
    active: Boolean(playingId),
    playingAlbum: mode === "album",
    audioRef,
    toggleTrack,
    toggleAlbum,
    stop,
    canPlayFile: (file) => Boolean(enabled) && isOnDisk(file) && isAudioFile(file),
    nowPlayingLabel: nowPlaying ? String(nowPlaying.filename || "") : "",
  };
}
