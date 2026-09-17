/** On-page album playback helpers (music / incoming-music work pages). */

export const AUDIO_EXTS = [".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".opus", ".wav", ".aac", ".wma"];

function fileLabel(row) {
  return String(row?.filename || row?.path || "");
}

function isOnDisk(row) {
  return row?.on_disk !== false;
}

export function fileExtension(name) {
  const text = String(name || "")
    .trim()
    .toLowerCase()
    .replace(/\\/g, "/");
  const base = text.slice(text.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot >= 0 ? base.slice(dot) : "";
}

export function isAudioFile(row) {
  return AUDIO_EXTS.includes(fileExtension(fileLabel(row)));
}

/** On-disk audio rows in catalog order (API already sorts by filename). */
export function playableTracks(files = []) {
  return (files || []).filter((row) => isOnDisk(row) && isAudioFile(row));
}

export function workStreamUrl(workId, fileId) {
  const id = String(workId || "").trim();
  const file = String(fileId || "").trim();
  if (!id || !file) return "";
  return `/api/works/${encodeURIComponent(id)}/stream?file=${encodeURIComponent(file)}`;
}

export function nextTrackAfter(tracks = [], fileId = "") {
  const wanted = String(fileId || "");
  const index = (tracks || []).findIndex((row) => String(row?.id || "") === wanted);
  if (index < 0 || index + 1 >= tracks.length) return null;
  return tracks[index + 1];
}

/**
 * Pure transition after a track ends.
 * Album mode advances; single mode (or end of album) clears playback.
 */
export function playerAfterEnded(state, tracks = []) {
  const playingId = String(state?.playingId || "");
  if (!playingId) return { playingId: null, mode: null };
  if (state?.mode !== "album") return { playingId: null, mode: null };
  const next = nextTrackAfter(tracks, playingId);
  if (!next) return { playingId: null, mode: null };
  return { playingId: String(next.id), mode: "album" };
}

export function playerToggleTrack(state, fileId) {
  const id = String(fileId || "");
  if (!id) return { playingId: null, mode: null };
  if (String(state?.playingId || "") === id) return { playingId: null, mode: null };
  return { playingId: id, mode: "single" };
}

export function playerToggleAlbum(state, tracks = []) {
  if (state?.playingId) return { playingId: null, mode: null };
  const first = (tracks || [])[0];
  if (!first?.id) return { playingId: null, mode: null };
  return { playingId: String(first.id), mode: "album" };
}
