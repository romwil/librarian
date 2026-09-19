import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  LISTEN_PERSIST_MIN_MS,
  chapterAt,
  chapterRemainingSeconds,
  decodeListenPosition,
  encodeListenPosition,
  formatListenClock,
  listenFraction,
  nextChapter,
  nextListenRate,
  nextSleepTimerId,
  playableTracks,
  prevChapter,
  shouldPersistListenCadence,
  shouldWriteListenProgress,
  sleepTimerLabel,
  workStreamUrl,
} from "../listen.js";

function coverUrl(work) {
  return work?.has_cover && work?.id ? `/api/works/${work.id}/cover` : "";
}

export default function AudiobookPlayer({
  work,
  files = [],
  fileId = "",
  progress = null,
  player = null,
  playerNote = "",
  onClose,
  onProgress,
}) {
  const audioRef = useRef(null);
  const tracks = playableTracks(files);
  const tracksRef = useRef(tracks);
  const persistTimer = useRef(0);
  const lastPersist = useRef({ fileId: "", seconds: 0, fraction: 0, at: 0 });
  const readyRef = useRef(false);
  const resumeSecondsRef = useRef(0);
  const bookmarkRef = useRef(decodeListenPosition(progress?.position || ""));
  const sleepDeadlineRef = useRef(0);
  const sleepChapterEndRef = useRef(false);

  const bookmark = decodeListenPosition(progress?.position || "");
  bookmarkRef.current = bookmark;
  const initialFile =
    String(fileId || "").trim() ||
    bookmark.fileId ||
    String(tracks[0]?.id || "");
  const [activeId, setActiveId] = useState(initialFile);
  const [chapters, setChapters] = useState([]);
  const [status, setStatus] = useState("Opening the volume…");
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(bookmark.seconds || 0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(bookmark.rate > 0 ? bookmark.rate : 1);
  const [sleepId, setSleepId] = useState("off");

  tracksRef.current = tracks;
  const fileIndex = Math.max(
    0,
    tracks.findIndex((row) => String(row.id) === String(activeId)),
  );
  const activeTrack = tracks[fileIndex] || tracks[0] || null;
  const chapter = chapterAt(chapters, currentTime);
  const chapterLeft = chapterRemainingSeconds(chapters, currentTime, duration);

  function persist(force = false) {
    if (!work?.id || !activeTrack) return;
    const audio = audioRef.current;
    const seconds = audio ? audio.currentTime : currentTime;
    if (
      !shouldWriteListenProgress({
        ready: readyRef.current,
        seconds,
        resumeSeconds: resumeSecondsRef.current,
        force,
      })
    ) {
      return;
    }
    if (
      !shouldPersistListenCadence({
        force,
        lastPersistMs: lastPersist.current.at,
        minIntervalMs: LISTEN_PERSIST_MIN_MS,
      })
    ) {
      return;
    }
    const dur = audio && audio.duration > 0 ? audio.duration : duration;
    const local = dur > 0 ? seconds / dur : 0;
    const fraction = listenFraction({
      fileIndex,
      fileCount: tracks.length,
      localFraction: local,
    });
    const body = {
      position: encodeListenPosition(String(activeTrack.id), seconds, { rate }),
      fraction,
    };
    const prev = lastPersist.current;
    if (
      !force &&
      prev.fileId === String(activeTrack.id) &&
      Math.abs(prev.seconds - seconds) < 2 &&
      Math.abs(prev.fraction - fraction) < 0.01
    ) {
      return;
    }
    lastPersist.current = {
      fileId: String(activeTrack.id),
      seconds,
      fraction,
      at: Date.now(),
    };
    window.clearTimeout(persistTimer.current);
    const run = () =>
      api
        .progress(work.id, body)
        .then((res) => {
          if (res?.progress && typeof onProgress === "function") onProgress(res.progress);
        })
        .catch(() => {});
    if (force) run();
    else persistTimer.current = window.setTimeout(run, LISTEN_PERSIST_MIN_MS);
  }

  function flushProgress() {
    window.clearTimeout(persistTimer.current);
    if (!readyRef.current) return;
    persist(true);
  }

  function markReady() {
    readyRef.current = true;
  }

  function loadTrack(nextId, seekSeconds = 0) {
    const audio = audioRef.current;
    const id = String(nextId || "");
    const src = workStreamUrl(work.id, id);
    if (!audio || !src) return;
    readyRef.current = false;
    resumeSecondsRef.current = Math.max(0, Number(seekSeconds) || 0);
    setActiveId(id);
    setStatus("Opening the volume…");
    setError("");
    audio.src = src;
    audio.playbackRate = rate;
    const onMeta = () => {
      audio.removeEventListener("loadedmetadata", onMeta);
      const target = resumeSecondsRef.current;
      if (target > 0 && Number.isFinite(target)) {
        const arm = () => {
          audio.removeEventListener("seeked", arm);
          markReady();
          setCurrentTime(audio.currentTime || target);
        };
        audio.addEventListener("seeked", arm);
        try {
          audio.currentTime = target;
        } catch {
          markReady();
        }
        window.setTimeout(() => {
          if (!readyRef.current) markReady();
        }, 400);
      } else {
        markReady();
      }
      setDuration(audio.duration || 0);
      setStatus("");
      const playAttempt = audio.play();
      if (playAttempt && typeof playAttempt.catch === "function") {
        playAttempt.catch(() => setPlaying(false));
      }
    };
    audio.addEventListener("loadedmetadata", onMeta);
    audio.load();
  }

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      const playAttempt = audio.play();
      if (playAttempt && typeof playAttempt.catch === "function") {
        playAttempt.catch(() => setPlaying(false));
      }
    } else {
      audio.pause();
    }
  }

  function seekTo(seconds) {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(seconds)) return;
    markReady();
    resumeSecondsRef.current = 0;
    audio.currentTime = Math.max(0, seconds);
    setCurrentTime(audio.currentTime);
    persist();
  }

  function skipSeconds(delta) {
    const audio = audioRef.current;
    if (!audio) return;
    seekTo((audio.currentTime || 0) + delta);
  }

  function jumpChapter(direction) {
    const target =
      direction < 0 ? prevChapter(chapters, currentTime) : nextChapter(chapters, currentTime);
    if (target) seekTo(Number(target.start) || 0);
    else if (direction < 0) seekTo(0);
  }

  function changeRate() {
    const next = nextListenRate(rate);
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
    if (readyRef.current) persist(true);
  }

  function cycleSleep() {
    const next = nextSleepTimerId(sleepId);
    setSleepId(next);
    sleepChapterEndRef.current = next === "chapter";
    if (next === "off" || next === "chapter") {
      sleepDeadlineRef.current = 0;
      return;
    }
    const minutes = Number(next) || 0;
    sleepDeadlineRef.current = Date.now() + minutes * 60 * 1000;
  }

  function maybeTripSleep(nowSeconds) {
    const audio = audioRef.current;
    if (!audio || audio.paused) return;
    if (sleepChapterEndRef.current) {
      const left = chapterRemainingSeconds(chapters, nowSeconds, duration);
      if (left <= 0.35) {
        audio.pause();
        setSleepId("off");
        sleepChapterEndRef.current = false;
        sleepDeadlineRef.current = 0;
      }
      return;
    }
    if (sleepDeadlineRef.current > 0 && Date.now() >= sleepDeadlineRef.current) {
      audio.pause();
      setSleepId("off");
      sleepDeadlineRef.current = 0;
    }
  }

  useEffect(() => {
    function onKey(event) {
      if (event.target?.closest?.("input, textarea, select, [contenteditable=true]")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key === " " || event.key === "k") {
        event.preventDefault();
        togglePlay();
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        skipSeconds(-15);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        skipSeconds(30);
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  useEffect(() => {
    if (!activeTrack?.id || !work?.id) {
      setError("This audiobook has no playable files on the shelf.");
      setStatus("");
      return undefined;
    }
    let alive = true;
    api
      .chapters(work.id, activeTrack.id)
      .then((data) => {
        if (!alive) return;
        setChapters(Array.isArray(data?.chapters) ? data.chapters : []);
      })
      .catch(() => {
        if (!alive) return;
        setChapters([]);
      });
    const mark = bookmarkRef.current;
    const resume =
      String(activeTrack.id) === String(mark.fileId || activeTrack.id) ? mark.seconds : 0;
    if (mark.rate > 0) setRate(mark.rate);
    loadTrack(activeTrack.id, resume);
    function onPageHide() {
      flushProgress();
    }
    function onVisibility() {
      if (document.visibilityState === "hidden") flushProgress();
    }
    window.addEventListener("pagehide", onPageHide);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      window.removeEventListener("pagehide", onPageHide);
      document.removeEventListener("visibilitychange", onVisibility);
      flushProgress();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount / file change only
  }, [work?.id, activeTrack?.id]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    function onTime() {
      const now = audio.currentTime || 0;
      setCurrentTime(now);
      if (audio.duration) setDuration(audio.duration);
      maybeTripSleep(now);
      persist();
    }
    function onPlay() {
      setPlaying(true);
    }
    function onPause() {
      setPlaying(false);
      persist(true);
    }
    function onEnded() {
      const next = tracksRef.current[fileIndex + 1];
      if (next?.id) {
        loadTrack(String(next.id), 0);
        return;
      }
      setPlaying(false);
      if (work?.id) {
        api.progress(work.id, { finished: true }).then((res) => {
          if (res?.progress && typeof onProgress === "function") onProgress(res.progress);
        }).catch(() => {});
      }
    }
    function onError() {
      setStatus("");
      setError(humanError(new Error("This file could not be streamed.")));
      setPlaying(false);
    }

    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onError);
    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
    };
  }, [fileIndex, work?.id, chapters, duration, sleepId]);

  useEffect(() => {
    if (!("mediaSession" in navigator) || !work) return undefined;
    const art = coverUrl(work);
    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title: work.title || "Audiobook",
        artist: work.author || "",
        album: chapter?.title || activeTrack?.filename || "Listening room",
        artwork: art ? [{ src: art, sizes: "512x512", type: "image/jpeg" }] : [],
      });
      navigator.mediaSession.setActionHandler("play", () => audioRef.current?.play());
      navigator.mediaSession.setActionHandler("pause", () => audioRef.current?.pause());
      navigator.mediaSession.setActionHandler("seekbackward", () => skipSeconds(-15));
      navigator.mediaSession.setActionHandler("seekforward", () => skipSeconds(30));
      navigator.mediaSession.setActionHandler("previoustrack", () => jumpChapter(-1));
      navigator.mediaSession.setActionHandler("nexttrack", () => jumpChapter(1));
      navigator.mediaSession.setActionHandler("seekto", (details) => {
        if (details?.seekTime != null) seekTo(details.seekTime);
      });
    } catch {
      /* Media Session is best-effort */
    }
    return () => {
      try {
        navigator.mediaSession.setActionHandler("play", null);
        navigator.mediaSession.setActionHandler("pause", null);
        navigator.mediaSession.setActionHandler("seekbackward", null);
        navigator.mediaSession.setActionHandler("seekforward", null);
        navigator.mediaSession.setActionHandler("previoustrack", null);
        navigator.mediaSession.setActionHandler("nexttrack", null);
        navigator.mediaSession.setActionHandler("seekto", null);
      } catch {
        /* ignore */
      }
    };
  }, [work, chapter?.title, activeTrack?.filename, chapters]);

  return (
    <div className="reader listen-room" role="dialog" aria-modal="true" aria-labelledby="listen-title" data-testid="listen-room">
      <header className="reader-head">
        <div className="reader-titleblock">
          <p className="kicker">Listening room</p>
          <h1 id="listen-title">{work.title}</h1>
        </div>
        <p className="muted reader-esc">Space play/pause · ← → skip · Esc closes</p>
        <button type="button" className="cta ghost compact" onClick={onClose} data-testid="listen-close">
          Close
        </button>
      </header>
      <div className="reader-stage listen-stage">
        {status ? <p className="reader-status">{status}</p> : null}
        {error ? <p className="reader-status alert">{error}</p> : null}
        <div className="listen-panel">
          <div className="listen-art" aria-hidden="true">
            {coverUrl(work) ? <img src={coverUrl(work)} alt="" /> : <span className="listen-cloth" />}
            <span className="cover-wave" />
          </div>
          <div className="listen-copy">
            <p className="muted">{work.author || "Unknown author"}</p>
            <p className="listen-chapter" data-testid="listen-chapter">
              {chapter?.title || activeTrack?.filename || "Audiobook"}
              {chapterLeft > 0 ? (
                <span className="muted" data-testid="listen-chapter-remaining">
                  {" "}
                  · {formatListenClock(chapterLeft)} left in chapter
                </span>
              ) : null}
            </p>
            <div className="listen-progress">
              <input
                type="range"
                min={0}
                max={Math.max(1, duration || 1)}
                step={1}
                value={Math.min(currentTime, duration || currentTime)}
                onChange={(event) => seekTo(Number(event.target.value))}
                aria-label="Listen position"
                data-testid="listen-seek"
              />
              <div className="listen-times muted">
                <span>{formatListenClock(currentTime)}</span>
                <span>{formatListenClock(duration)}</span>
              </div>
            </div>
            <div className="cta-row compact listen-controls">
              <button type="button" className="cta outline compact" onClick={() => jumpChapter(-1)}>
                Chapter −
              </button>
              <button type="button" className="cta outline compact" onClick={() => skipSeconds(-15)}>
                −15s
              </button>
              <button type="button" className="cta compact" onClick={togglePlay} data-testid="listen-toggle">
                {playing ? "Pause" : "Play"}
              </button>
              <button type="button" className="cta outline compact" onClick={() => skipSeconds(30)}>
                +30s
              </button>
              <button type="button" className="cta outline compact" onClick={() => jumpChapter(1)}>
                Chapter +
              </button>
              <button type="button" className="cta ghost compact" onClick={changeRate} data-testid="listen-rate">
                {rate}×
              </button>
              <button type="button" className="cta ghost compact" onClick={cycleSleep} data-testid="listen-sleep">
                {sleepTimerLabel(sleepId)}
              </button>
            </div>
            {tracks.length > 1 ? (
              <ul className="file-list listen-files" data-testid="listen-files">
                {tracks.map((row, index) => (
                  <li key={row.id} className={String(row.id) === String(activeId) ? "is-playing" : undefined}>
                    <button type="button" className="file-list-open" onClick={() => loadTrack(String(row.id), 0)}>
                      {row.filename || `Part ${index + 1}`}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {chapters.length ? (
              <ul className="listen-chapters" data-testid="listen-chapters">
                {chapters.map((row) => (
                  <li key={`${row.index}-${row.start}`}>
                    <button type="button" className="chip" onClick={() => seekTo(Number(row.start) || 0)}>
                      {row.title || `Chapter ${(row.index || 0) + 1}`}
                      <span className="muted"> · {formatListenClock(row.start)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {player?.href ? (
              <p className="listen-external">
                <a className="cta outline compact" href={player.href} target="_blank" rel="noreferrer" data-testid="listen-open-player">
                  {player.label || "Open in player"}
                </a>
              </p>
            ) : playerNote ? (
              <p className="muted" data-testid="listen-player-note">
                {playerNote}
              </p>
            ) : null}
          </div>
        </div>
      </div>
      <audio ref={audioRef} preload="metadata" hidden data-testid="listen-audio" />
    </div>
  );
}
