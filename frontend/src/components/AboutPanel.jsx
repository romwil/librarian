import { useEffect, useState } from "react";
import { api } from "../api.js";
import { fetchReleaseNotes, normalizeReleaseNotes } from "../lib/releaseNotes.js";
import ReleaseNotesPanel from "./ReleaseNotesPanel.jsx";

/**
 * Settings → About: runtime version, optional build stamp, full release notes.
 */
export default function AboutPanel() {
  const [version, setVersion] = useState("");
  const [build, setBuild] = useState("");
  const [releases, setReleases] = useState([]);
  const [notesError, setNotesError] = useState("");
  const [notesLoading, setNotesLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((data) => {
        if (cancelled) return;
        setVersion(String(data?.version || "").trim());
        setBuild(String(data?.build || "").trim());
      })
      .catch(() => {
        if (cancelled) return;
        setVersion("");
        setBuild("");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setNotesLoading(true);
    fetchReleaseNotes()
      .then((payload) => {
        if (cancelled) return;
        setReleases(normalizeReleaseNotes(payload));
        setNotesError("");
        setNotesLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setReleases([]);
        setNotesError("Could not load release notes.");
        setNotesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="more-settings settings-about" id="about" data-testid="settings-about" aria-labelledby="settings-about-heading">
      <p className="kicker" id="settings-about-heading">
        About
      </p>
      <h2>Librarian</h2>
      <p className="lede">Version, build stamp, and What’s New from CHANGELOG.</p>
      {version ? (
        <p className="muted" data-testid="settings-about-version">
          Running {version}
          {build ? <span data-testid="settings-about-build"> · {build}</span> : null}
        </p>
      ) : (
        <p className="muted" data-testid="settings-about-version-pending">
          Reading version…
        </p>
      )}

      <section
        className="settings-release-notes"
        id="release-notes"
        aria-labelledby="settings-release-notes-heading"
      >
        <p className="kicker" id="settings-release-notes-heading">
          What’s New
        </p>
        <p className="lede">Full history from CHANGELOG — newest first.</p>
        {notesError ? (
          <p className="alert" data-testid="settings-release-notes-error">
            {notesError}
          </p>
        ) : notesLoading ? (
          <p className="muted" data-testid="settings-release-notes-loading">
            Loading release notes…
          </p>
        ) : (
          <ReleaseNotesPanel releases={releases} showJumpLinks scrollable testId="settings-release-notes" />
        )}
      </section>
    </section>
  );
}
