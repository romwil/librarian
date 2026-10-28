import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { canListenInApp } from "../listen.js";
import { canReadInApp } from "../reader.js";

export function workCanRead(data) {
  return Boolean(data?.can_read) && canReadInApp(data.work, data.files);
}

export function workCanListen(data) {
  return Boolean(data?.listen?.can_listen) && canListenInApp(data.work, data.files, Boolean(data.can_download));
}

/**
 * Reading room / Listening room open state for a work page, kept in step with
 * the shareable `?read=1&file=` / `?listen=1&file=` deep links (same contract
 * as WorkPeek's `workReaderPath`).
 */
export function useWorkRooms({ id, data, setData }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [reading, setReading] = useState(false);
  const [readingFileId, setReadingFileId] = useState("");
  const [listening, setListening] = useState(false);
  const [listeningFileId, setListeningFileId] = useState("");

  useEffect(() => {
    if (!data) return;
    if (searchParams.get("listen") === "1" && workCanListen(data)) {
      setListeningFileId(searchParams.get("file") || "");
      setListening(true);
      return;
    }
    if (searchParams.get("read") === "1" && workCanRead(data)) {
      setReadingFileId(searchParams.get("file") || "");
      setReading(true);
    }
  }, [searchParams, data]);

  function openReader(fileId = "") {
    const wanted = String(fileId || "").trim();
    setReadingFileId(wanted);
    setReading(true);
    const next = new URLSearchParams(searchParams);
    next.delete("listen");
    next.set("read", "1");
    if (wanted) next.set("file", wanted);
    else next.delete("file");
    setSearchParams(next, { replace: true });
  }

  function closeReader() {
    setReading(false);
    setReadingFileId("");
    if (searchParams.get("read") || searchParams.get("file")) {
      const next = new URLSearchParams(searchParams);
      next.delete("read");
      next.delete("file");
      setSearchParams(next, { replace: true });
    }
  }

  async function openListen(fileId = "") {
    const wanted = String(fileId || "").trim();
    setListeningFileId(wanted);
    // Refresh per-user progress so resume is not stale after a prior Listen session.
    try {
      const fresh = await api.work(id);
      setData(fresh);
    } catch {
      /* keep existing payload */
    }
    setListening(true);
    const next = new URLSearchParams(searchParams);
    next.delete("read");
    next.set("listen", "1");
    if (wanted) next.set("file", wanted);
    else next.delete("file");
    setSearchParams(next, { replace: true });
  }

  function closeListen() {
    setListening(false);
    setListeningFileId("");
    if (searchParams.get("listen") || searchParams.get("file")) {
      const next = new URLSearchParams(searchParams);
      next.delete("listen");
      next.delete("file");
      setSearchParams(next, { replace: true });
    }
    api
      .work(id)
      .then(setData)
      .catch(() => {});
  }

  return {
    reading,
    readingFileId,
    listening,
    listeningFileId,
    openReader,
    closeReader,
    openListen,
    closeListen,
  };
}
