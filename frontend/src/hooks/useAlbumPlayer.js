import { useEffect, useState } from "react";
import {
  isAudioFile,
  playableTracks,
  playerAfterEnded,
  playerToggleAlbum,
  playerToggleTrack,
  workStreamUrl,
} from "../music.js";
import { useAudioTransport } from "./useAudioTransport.js";

function isOnDisk(row) {
  return row?.on_disk !== false;
}

/**
 * Music queue for a work page — one track or the whole album — on the shared
 * audio transport. Attach audioRef to a single <audio preload="none"> on the page.
 */
export function useAlbumPlayer({ workId, files = [], enabled = false }) {
  const [playingId, setPlayingId] = useState(null);
  const [mode, setMode] = useState(null);
  const tracks = enabled ? playableTracks(files) : [];

  const transport = useAudioTransport({
    onPlayRejected: () => stop(),
    onEnded: () => {
      const next = playerAfterEnded({ playingId, mode }, tracks);
      if (!next.playingId) {
        stop();
        return;
      }
      loadAndPlay(next.playingId, next.mode);
    },
  });

  function applyState(next) {
    setPlayingId(next.playingId);
    setMode(next.mode);
  }

  function stop() {
    transport.silence();
    applyState({ playingId: null, mode: null });
  }

  function loadAndPlay(fileId, nextMode) {
    const id = String(fileId || "");
    if (!transport.start(workStreamUrl(workId, id))) {
      stop();
      return;
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

  const { silence } = transport;
  useEffect(() => {
    silence();
    applyState({ playingId: null, mode: null });
  }, [workId, silence]);

  const nowPlaying = tracks.find((row) => String(row.id) === String(playingId || "")) || null;

  return {
    enabled: Boolean(enabled) && tracks.length > 0,
    tracks,
    playingId,
    active: Boolean(playingId),
    playingAlbum: mode === "album",
    audioRef: transport.audioRef,
    toggleTrack,
    toggleAlbum,
    stop,
    canPlayFile: (file) => Boolean(enabled) && isOnDisk(file) && isAudioFile(file),
    nowPlayingLabel: nowPlaying ? String(nowPlaying.filename || "") : "",
  };
}
