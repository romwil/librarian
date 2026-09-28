import { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  fetchReleaseNotes,
  getLastSeenVersion,
  normalizeReleaseNotes,
  setLastSeenVersion,
  shouldShowWhatsNew,
  truthfulReleaseForVersion,
} from "../lib/releaseNotes.js";
import WhatsNewModal from "./WhatsNewModal.jsx";

/**
 * Compares runtime /api/health version to localStorage last-seen.
 * Shows What’s New when last-seen is missing or older than runtime.
 * Notes only render when release-notes.json has an exact version match —
 * never a newer/older story that would lie about this deploy.
 * Dismiss / Read full notes persist last-seen = runtime (no silent seed).
 */
export default function WhatsNewGate() {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState("");
  const [release, setRelease] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function evaluate() {
      try {
        const health = await api.health();
        const runtimeVersion = String(health?.version || "").trim();
        if (!runtimeVersion || cancelled) return;

        const lastSeen = getLastSeenVersion();
        if (!shouldShowWhatsNew(runtimeVersion, lastSeen)) return;

        let matched = null;
        try {
          const payload = await fetchReleaseNotes();
          const releases = normalizeReleaseNotes(payload);
          matched = truthfulReleaseForVersion(releases, runtimeVersion);
        } catch {
          matched = null;
        }

        if (cancelled) return;
        setVersion(runtimeVersion);
        setRelease(matched);
        setOpen(true);
      } catch {
        // Health unavailable — skip quietly.
      }
    }

    evaluate();
    return () => {
      cancelled = true;
    };
  }, []);

  function dismiss() {
    if (version) setLastSeenVersion(version);
    setOpen(false);
  }

  function onReadFull() {
    if (version) setLastSeenVersion(version);
    setOpen(false);
  }

  return (
    <WhatsNewModal
      open={open}
      version={version}
      release={release}
      onDismiss={dismiss}
      onReadFull={onReadFull}
    />
  );
}
