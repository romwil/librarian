/** Audiobook Listen helpers — deep links, bookmarks, chapters. */

import { isAudioFile, playableTracks, workStreamUrl } from "./music.js";

export const LISTEN_RATES = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5];
export const SLEEP_TIMER_OPTIONS = [
  { id: "off", label: "Sleep off", minutes: 0 },
  { id: "15", label: "Sleep 15m", minutes: 15 },
  { id: "30", label: "Sleep 30m", minutes: 30 },
  { id: "45", label: "Sleep 45m", minutes: 45 },
  { id: "chapter", label: "Sleep end of chapter", minutes: 0, endChapter: true },
];

/** Persist at most about once every `minIntervalMs` unless forced. */
export const LISTEN_PERSIST_MIN_MS = 900;

export function canListenInApp(work, files = [], canDownload = false) {
  if (work?.kind !== "audiobook") return false;
  if (!canDownload) return false;
  return playableTracks(files).length > 0;
}

export function workListenPath(workId, fileId = "") {
  const base = `/works/${encodeURIComponent(workId)}?listen=1`;
  const wanted = String(fileId || "").trim();
  return wanted ? `${base}&file=${encodeURIComponent(wanted)}` : base;
}

export function encodeListenPosition(fileId = "", seconds = 0, extras = {}) {
  const fid = String(fileId || "").trim();
  const secs = Math.max(0, Number(seconds) || 0);
  const rate = Number(extras?.rate);
  if (!fid && secs <= 0) return "";
  const payload = { file: fid, t: Math.round(secs * 1000) / 1000 };
  if (Number.isFinite(rate) && rate > 0 && rate !== 1) {
    payload.rate = Math.round(rate * 100) / 100;
  }
  return JSON.stringify(payload);
}

export function decodeListenPosition(raw = "") {
  const text = String(raw || "").trim();
  if (!text) return { fileId: "", seconds: 0, rate: 0 };
  if (text.startsWith("{")) {
    try {
      const data = JSON.parse(text);
      const rate = Number(data?.rate);
      return {
        fileId: String(data?.file || data?.file_id || "").trim(),
        seconds: Math.max(0, Number(data?.t ?? data?.seconds) || 0),
        rate: Number.isFinite(rate) && rate > 0 ? rate : 0,
      };
    } catch {
      return { fileId: "", seconds: 0, rate: 0 };
    }
  }
  const colon = text.lastIndexOf(":");
  if (colon > 0) {
    const secs = Number(text.slice(colon + 1));
    if (Number.isFinite(secs)) {
      return { fileId: text.slice(0, colon).trim(), seconds: Math.max(0, secs), rate: 0 };
    }
  }
  return { fileId: text, seconds: 0, rate: 0 };
}

/** Gate writes so pre-seek / Strict Mode remount at t=0 cannot wipe a bookmark. */
export function shouldWriteListenProgress({
  ready = false,
  seconds = 0,
  resumeSeconds = 0,
  force = false,
} = {}) {
  if (!ready && !force) return false;
  const now = Math.max(0, Number(seconds) || 0);
  const resume = Math.max(0, Number(resumeSeconds) || 0);
  // Never replace a real bookmark with a near-zero write before playback has advanced.
  if (resume >= 2 && now < 1) return false;
  return true;
}

/** Cadence gate for progress POSTs — force always writes. */
export function shouldPersistListenCadence({
  force = false,
  lastPersistMs = 0,
  nowMs = Date.now(),
  minIntervalMs = LISTEN_PERSIST_MIN_MS,
} = {}) {
  if (force) return true;
  return nowMs - Number(lastPersistMs || 0) >= Number(minIntervalMs || LISTEN_PERSIST_MIN_MS);
}

export function nextListenRate(current = 1, rates = LISTEN_RATES) {
  const list = Array.isArray(rates) && rates.length ? rates : LISTEN_RATES;
  const idx = list.findIndex((value) => Math.abs(Number(value) - Number(current)) < 0.001);
  if (idx < 0) return list[0];
  return list[(idx + 1) % list.length];
}

export function chapterRemainingSeconds(chapters = [], seconds = 0, duration = 0) {
  const t = Math.max(0, Number(seconds) || 0);
  const nxt = nextChapter(chapters, t);
  if (nxt) return Math.max(0, Number(nxt.start) - t);
  const dur = Math.max(0, Number(duration) || 0);
  if (dur > t) return dur - t;
  return 0;
}

export function sleepTimerLabel(optionId = "off") {
  const hit = SLEEP_TIMER_OPTIONS.find((row) => row.id === optionId);
  return hit?.label || "Sleep off";
}

export function nextSleepTimerId(current = "off") {
  const idx = SLEEP_TIMER_OPTIONS.findIndex((row) => row.id === current);
  const next = SLEEP_TIMER_OPTIONS[(Math.max(0, idx) + 1) % SLEEP_TIMER_OPTIONS.length];
  return next.id;
}

export function splitContinueRails(items = []) {
  const reading = [];
  const listening = [];
  for (const row of items || []) {
    if (String(row?.kind || "") === "audiobook") listening.push(row);
    else reading.push(row);
  }
  return { reading, listening };
}

export function listenFraction({ fileIndex = 0, fileCount = 1, localFraction = 0 } = {}) {
  const count = Math.max(1, Number(fileCount) || 1);
  const index = Math.max(0, Math.min(count - 1, Number(fileIndex) || 0));
  const local = Math.max(0, Math.min(1, Number(localFraction) || 0));
  return Math.max(0, Math.min(0.999, (index + local) / count));
}

export function chapterAt(chapters = [], seconds = 0) {
  const t = Math.max(0, Number(seconds) || 0);
  let current = null;
  for (const row of chapters || []) {
    if (Number(row?.start) <= t) current = row;
    else break;
  }
  return current;
}

export function nextChapter(chapters = [], seconds = 0) {
  const t = Math.max(0, Number(seconds) || 0);
  return (chapters || []).find((row) => Number(row?.start) > t + 0.25) || null;
}

export function prevChapter(chapters = [], seconds = 0) {
  const t = Math.max(0, Number(seconds) || 0);
  const current = chapterAt(chapters, t);
  if (current && t - Number(current.start || 0) > 1.5) return current;
  let prev = null;
  for (const row of chapters || []) {
    if (current && row === current) break;
    if (Number(row?.start) < t) prev = row;
  }
  return prev;
}

export function formatListenClock(seconds = 0) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export { isAudioFile, playableTracks, workStreamUrl };
