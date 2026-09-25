import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import {
  busyLabel,
  enrichIsRunning,
  enrichProgressSummary,
  scanIsRunning,
  scanProgressSummary,
} from "../actionBusy.js";
import AddToLibrary from "../components/AddToLibrary.jsx";
import MaintainStatusDock from "../components/MaintainStatusDock.jsx";
import { FieldLabel } from "../components/FieldHelp.jsx";
import { FIELD_HELP, humanError } from "../copy.js";
import { bestsellersHref } from "../find.js";
import {
  extraFilesReprocessIsRunning,
  extraFilesReprocessProgressSummary,
} from "../review.js";

function purgeShellsIsRunning(status) {
  return String(status?.status || "") === "running";
}

function purgeShellsProgressSummary(status) {
  if (!status) return "";
  const state = String(status.status || "");
  if (state === "failed") return status.error || "Purge shells failed.";
  if (state === "completed") {
    const purged = Number(status.purged ?? status.result?.purged) || 0;
    const kept = Number(status.kept ?? status.result?.kept) || 0;
    return `Purged ${purged} shell${purged === 1 ? "" : "s"} · kept ${kept}`;
  }
  if (state !== "running") return "";
  const done = Number(status.done) || 0;
  const total = Number(status.total) || 0;
  const purged = Number(status.purged) || 0;
  if (total > 0) return `Purging shells… ${done} of ${total} · removed ${purged}`;
  return status.phase ? `Purging shells… ${status.phase}` : "Purging shells…";
}

function splitMixedIsRunning(status) {
  return String(status?.status || "") === "running";
}

function splitMixedProgressSummary(status) {
  if (!status) return "";
  const state = String(status.status || "");
  if (state === "failed") return status.error || "Split mixed kinds failed.";
  if (state === "completed") {
    const split = Number(status.split ?? status.result?.split) || 0;
    const failed = Number(status.failed ?? status.result?.failed) || 0;
    return `Split ${split} blend${split === 1 ? "" : "s"}${failed ? ` · ${failed} failed` : ""}`;
  }
  if (state !== "running") return "";
  const done = Number(status.done) || 0;
  const total = Number(status.total) || 0;
  const split = Number(status.split) || 0;
  if (total > 0) return `Splitting blends… ${done} of ${total} · split ${split}`;
  return status.phase ? `Splitting blends… ${status.phase}` : "Splitting blends…";
}

export default function MaintainPage() {
  const { user } = useOutletContext() || {};
  const [scan, setScan] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState(null);
  const scanPollRef = useRef(0);
  const [enrich, setEnrich] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [enrichStatus, setEnrichStatus] = useState(null);
  const enrichPollRef = useRef(0);
  const [suggestNote, setSuggestNote] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [shelfHealth, setShelfHealth] = useState(null);
  const [shelfHealthError, setShelfHealthError] = useState("");
  const [goodreads, setGoodreads] = useState("");
  const [importing, setImporting] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [extraNote, setExtraNote] = useState("");
  const [extraClearing, setExtraClearing] = useState(false);
  const [extraBacklog, setExtraBacklog] = useState(0);
  const extraPollRef = useRef(0);
  const [shellNote, setShellNote] = useState("");
  const [shellPurging, setShellPurging] = useState(false);
  const [shellBacklog, setShellBacklog] = useState(0);
  const [shellStatus, setShellStatus] = useState(null);
  const shellPollRef = useRef(0);
  const [mixNote, setMixNote] = useState("");
  const [mixSplitting, setMixSplitting] = useState(false);
  const [mixBacklog, setMixBacklog] = useState(0);
  const [mixStatus, setMixStatus] = useState(null);
  const mixPollRef = useRef(0);

  useEffect(() => {
    if (user?.role !== "owner") return undefined;
    let cancelled = false;
    api
      .enrichStatus()
      .then((status) => {
        if (cancelled) return;
        setEnrichStatus(status);
        if (enrichIsRunning(status)) {
          setEnriching(true);
          setEnrich(enrichProgressSummary(status) || busyLabel("enrich"));
        }
      })
      .catch(() => {});
    api
      .scanStatus()
      .then((status) => {
        if (cancelled) return;
        setScanStatus(status);
        if (scanIsRunning(status)) {
          setScanning(true);
          setScan(scanProgressSummary(status) || busyLabel("scan"));
        }
      })
      .catch(() => {});
    api
      .reviewReprocessExtraFilesStatus()
      .then((status) => {
        if (cancelled) return;
        if (status?.extra_files_remaining != null) {
          setExtraBacklog(Number(status.extra_files_remaining) || 0);
        }
        if (extraFilesReprocessIsRunning(status)) {
          setExtraClearing(true);
          setExtraNote(extraFilesReprocessProgressSummary(status) || "Clearing extra-files…");
        }
      })
      .catch(() => {});
    api
      .review()
      .then((data) => {
        if (cancelled) return;
        if (data.extra_files_count != null) {
          setExtraBacklog(Number(data.extra_files_count) || 0);
        }
      })
      .catch(() => {});
    api
      .maintainPurgeShellsStatus()
      .then((status) => {
        if (cancelled) return;
        setShellStatus(status);
        if (status?.shells_remaining != null) {
          setShellBacklog(Number(status.shells_remaining) || 0);
        }
        if (purgeShellsIsRunning(status)) {
          setShellPurging(true);
          setShellNote(purgeShellsProgressSummary(status) || "Purging shells…");
        }
      })
      .catch(() => {});
    api
      .maintainSplitMixedKindsStatus()
      .then((status) => {
        if (cancelled) return;
        setMixStatus(status);
        if (status?.mixed_remaining != null) {
          setMixBacklog(Number(status.mixed_remaining) || 0);
        }
        if (splitMixedIsRunning(status)) {
          setMixSplitting(true);
          setMixNote(splitMixedProgressSummary(status) || "Splitting blends…");
        }
      })
      .catch(() => {});
    api
      .maintainShelfHealth()
      .then((data) => {
        if (cancelled) return;
        setShelfHealth(data);
        setShelfHealthError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setShelfHealthError(humanError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [user?.role]);

  useEffect(() => {
    if (!scanning) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const status = await api.scanStatus();
        if (cancelled) return;
        setScanStatus(status);
        const summary = scanProgressSummary(status);
        if (summary) setScan(summary);
        if (scanIsRunning(status)) {
          scanPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setScanning(false);
        if (status?.status === "failed") setScan(status.error || "Scan failed.");
        else if (status?.status === "completed") setScan(summary || "Scan finished.");
      } catch (err) {
        if (cancelled) return;
        setScanning(false);
        setScan(humanError(err));
      }
    }
    scanPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(scanPollRef.current);
    };
  }, [scanning]);

  useEffect(() => {
    if (!enriching) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const status = await api.enrichStatus();
        if (cancelled) return;
        setEnrichStatus(status);
        const summary = enrichProgressSummary(status);
        if (summary) setEnrich(summary);
        if (enrichIsRunning(status)) {
          enrichPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setEnriching(false);
        if (status?.status === "failed") setEnrich(status.error || "Enrich failed.");
        else if (status?.status === "completed") setEnrich(summary || "Enrich finished.");
      } catch (err) {
        if (cancelled) return;
        setEnriching(false);
        setEnrich(humanError(err));
      }
    }
    enrichPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(enrichPollRef.current);
    };
  }, [enriching]);

  useEffect(() => {
    if (!extraClearing) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const status = await api.reviewReprocessExtraFilesStatus();
        if (cancelled) return;
        if (status?.extra_files_remaining != null) {
          setExtraBacklog(Number(status.extra_files_remaining) || 0);
        }
        const summary = extraFilesReprocessProgressSummary(status);
        if (summary) setExtraNote(summary);
        if (extraFilesReprocessIsRunning(status)) {
          extraPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setExtraClearing(false);
        if (status?.status === "failed") setExtraNote(status.error || "Clear extra-files failed.");
        else if (status?.status === "completed") setExtraNote(summary || "Finished clearing extra-files slips.");
      } catch (err) {
        if (cancelled) return;
        setExtraClearing(false);
        setExtraNote(humanError(err));
      }
    }
    extraPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(extraPollRef.current);
    };
  }, [extraClearing]);

  useEffect(() => {
    if (!shellPurging) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const status = await api.maintainPurgeShellsStatus();
        if (cancelled) return;
        setShellStatus(status);
        if (status?.shells_remaining != null) {
          setShellBacklog(Number(status.shells_remaining) || 0);
        }
        const summary = purgeShellsProgressSummary(status);
        if (summary) setShellNote(summary);
        if (purgeShellsIsRunning(status)) {
          shellPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setShellPurging(false);
        if (status?.status === "failed") setShellNote(status.error || "Purge shells failed.");
        else if (status?.status === "completed") setShellNote(summary || "Finished purging shells.");
      } catch (err) {
        if (cancelled) return;
        setShellPurging(false);
        setShellNote(humanError(err));
      }
    }
    shellPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(shellPollRef.current);
    };
  }, [shellPurging]);

  useEffect(() => {
    if (!mixSplitting) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const status = await api.maintainSplitMixedKindsStatus();
        if (cancelled) return;
        setMixStatus(status);
        if (status?.mixed_remaining != null) {
          setMixBacklog(Number(status.mixed_remaining) || 0);
        }
        const summary = splitMixedProgressSummary(status);
        if (summary) setMixNote(summary);
        if (splitMixedIsRunning(status)) {
          mixPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setMixSplitting(false);
        if (status?.status === "failed") setMixNote(status.error || "Split mixed kinds failed.");
        else if (status?.status === "completed") setMixNote(summary || "Finished splitting blends.");
      } catch (err) {
        if (cancelled) return;
        setMixSplitting(false);
        setMixNote(humanError(err));
      }
    }
    mixPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(mixPollRef.current);
    };
  }, [mixSplitting]);

  if (!user) return null;
  if (user.role !== "owner") {
    return <Navigate to="/" replace />;
  }

  async function startScanShelves() {
    setScan("");
    setScanning(true);
    setScanStatus({
      status: "running",
      phase: "starting",
      logs: ["Starting scan…"],
      done: 0,
      total: 0,
      created: 0,
      updated: 0,
      review: 0,
      errors: 0,
    });
    try {
      const started = await api.scanShelves();
      setScanStatus(started);
      setScan(scanProgressSummary(started) || busyLabel("scan"));
      if (!scanIsRunning(started) && started?.status === "completed") {
        setScanning(false);
        setScan(scanProgressSummary(started) || "Scan finished.");
      }
    } catch (err) {
      setScanning(false);
      setScan(humanError(err));
    }
  }

  async function startEnrichShelves() {
    setEnrich("");
    setEnriching(true);
    setEnrichStatus({
      status: "running",
      phase: "starting",
      logs: ["Starting enrich…"],
      done: 0,
      total: 0,
      updated: 0,
      skipped: 0,
      errors: 0,
    });
    try {
      const started = await api.enrichShelves();
      setEnrichStatus(started);
      setEnrich(enrichProgressSummary(started) || busyLabel("enrich"));
      if (!enrichIsRunning(started) && started?.status === "completed") {
        setEnriching(false);
        setEnrich(enrichProgressSummary(started) || "Enrich finished.");
      }
    } catch (err) {
      setEnriching(false);
      setEnrich(humanError(err));
    }
  }

  async function clearExtraFiles() {
    setExtraClearing(true);
    setExtraNote("Clearing extra-files…");
    try {
      const started = await api.reviewReprocessExtraFiles();
      if (started?.extra_files_remaining != null) {
        setExtraBacklog(Number(started.extra_files_remaining) || 0);
      }
      setExtraNote(extraFilesReprocessProgressSummary(started) || "Clearing extra-files…");
      if (!extraFilesReprocessIsRunning(started) && started?.status === "completed") {
        setExtraClearing(false);
        setExtraNote(extraFilesReprocessProgressSummary(started) || "Finished clearing extra-files slips.");
      }
    } catch (err) {
      setExtraClearing(false);
      setExtraNote(humanError(err));
    }
  }

  async function purgeShells() {
    setShellPurging(true);
    setShellNote("Purging shells…");
    try {
      const started = await api.maintainPurgeShells();
      setShellStatus(started);
      if (started?.shells_remaining != null) {
        setShellBacklog(Number(started.shells_remaining) || 0);
      }
      setShellNote(purgeShellsProgressSummary(started) || "Purging shells…");
      if (!purgeShellsIsRunning(started) && started?.status === "completed") {
        setShellPurging(false);
        setShellNote(purgeShellsProgressSummary(started) || "Finished purging shells.");
      }
    } catch (err) {
      setShellPurging(false);
      setShellNote(humanError(err));
    }
  }

  async function splitMixedKinds() {
    setMixSplitting(true);
    setMixNote("Splitting blends…");
    try {
      const started = await api.maintainSplitMixedKinds();
      setMixStatus(started);
      if (started?.mixed_remaining != null) {
        setMixBacklog(Number(started.mixed_remaining) || 0);
      }
      setMixNote(splitMixedProgressSummary(started) || "Splitting blends…");
      if (!splitMixedIsRunning(started) && started?.status === "completed") {
        setMixSplitting(false);
        setMixNote(splitMixedProgressSummary(started) || "Finished splitting blends.");
      }
    } catch (err) {
      setMixSplitting(false);
      setMixNote(humanError(err));
    }
  }

  return (
    <div className="admin-room maintain-page" data-testid="maintain-page">
      <p className="kicker">Owner</p>
      <h1>Maintain</h1>
      <p className="lede">
        Library grooming — curated lists, add on disk, scan, enrich, and Review. Credentials stay in{" "}
        <Link to="/settings">Settings</Link>.
      </p>

      <MaintainStatusDock />

      <section className="maintain-section" data-testid="maintain-curated">
        <p className="kicker">Curated</p>
        <h2>Bestsellers / curated lists</h2>
        <p className="lede">Chase hardcover lists with the household LLM. Beyond the shelves when a title is missing.</p>
        <div className="cta-row">
          <Link className="cta outline" to={bestsellersHref()} data-testid="maintain-bestsellers">
            Open bestsellers
          </Link>
        </div>
      </section>

      <section className="maintain-section" data-testid="maintain-ingest">
        <p className="kicker">Already on disk</p>
        <h2>Add a volume</h2>
        <AddToLibrary embedded />
      </section>

      <section className="maintain-section" data-testid="maintain-review">
        <p className="kicker">Review</p>
        <h2>Slips and extra files</h2>
        <p className="lede">
          Open the Review bag for identity slips. Clear extra-files reprocesses Calibre dumps that landed as extras.
        </p>
        <div className="cta-row">
          <Link className="cta outline" to="/review" data-testid="maintain-review-link">
            Open Review
          </Link>
          <button
            type="button"
            className="cta outline"
            disabled={extraClearing}
            aria-busy={extraClearing || undefined}
            onClick={clearExtraFiles}
            data-testid="maintain-clear-extra-files"
          >
            {extraClearing
              ? "Clearing…"
              : extraBacklog > 0
                ? `Clear extra-files (${extraBacklog})`
                : "Clear extra-files"}
          </button>
        </div>
        {extraNote ? <p className="muted">{extraNote}</p> : null}
      </section>

      <section className="maintain-section" data-testid="maintain-shells">
        <p className="kicker">Catalog</p>
        <h2>Purge unshelved shells</h2>
        <p className="lede">
          Remove catalog rows that never got a file on the shelf — dismissed Review slips and dump-title ghosts.
          Volumes that still have media on disk are kept.
        </p>
        <div className="cta-row">
          <button
            type="button"
            className="cta outline"
            disabled={shellPurging}
            aria-busy={shellPurging || undefined}
            onClick={purgeShells}
            data-testid="maintain-purge-shells"
          >
            {shellPurging
              ? "Purging…"
              : shellBacklog > 0
                ? `Purge shells (${shellBacklog})`
                : "Purge shells"}
          </button>
        </div>
        {shellNote ? <p className="muted">{shellNote}</p> : null}
        {shellStatus && shellPurging ? (
          <p className="sr-only" data-testid="maintain-purge-shells-running">
            Purge shells running
          </p>
        ) : null}
      </section>

      <section className="maintain-section" data-testid="maintain-split-mixed">
        <p className="kicker">Catalog</p>
        <h2>Split comic / book blends</h2>
        <p className="lede">
          Mass-import sometimes shelved a comic archive next to ebook formats under one work. This peels the ebooks
          onto their own book volume — media stays on disk.
        </p>
        <div className="cta-row">
          <button
            type="button"
            className="cta outline"
            disabled={mixSplitting}
            aria-busy={mixSplitting || undefined}
            onClick={splitMixedKinds}
            data-testid="maintain-split-mixed-kinds"
          >
            {mixSplitting
              ? "Splitting…"
              : mixBacklog > 0
                ? `Split blends (${mixBacklog})`
                : "Split comic/book blends"}
          </button>
        </div>
        {mixNote ? <p className="muted">{mixNote}</p> : null}
        {mixStatus && mixSplitting ? (
          <p className="sr-only" data-testid="maintain-split-mixed-running">
            Split mixed kinds running
          </p>
        ) : null}
      </section>

      <section className="maintain-section" data-testid="maintain-shelf-health">
        <p className="kicker">Shelves</p>
        <h2>Shelf health</h2>
        <p className="lede">
          Rescan library roots and fill thin metadata. Job progress stays in the telemetry dock above. Paths and
          tokens live in Settings.
        </p>
        {shelfHealth ? (
          <div className="shelf-health-report" data-testid="maintain-shelf-health-report">
            <p className="muted">
              {shelfHealth.ok
                ? "Library roots look writable for the lamp."
                : `${shelfHealth.locked_count} root${shelfHealth.locked_count === 1 ? "" : "s"} locked for the lamp.`}
            </p>
            <ul className="shelf-health-roots">
              {(shelfHealth.roots || []).map((root) => (
                <li key={root.field} data-testid={`shelf-health-root-${root.field}`}>
                  <span>{root.label}</span>
                  <span className="muted">
                    {root.writable ? "writable" : root.detail || "not writable"}
                    {root.path ? ` · ${root.path}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            <p className="lede shelf-health-chown" data-testid="maintain-shelf-health-chown">
              {shelfHealth.chown_tip || (
                <>
                  If Review Apply says a folder is locked for the lamp, on the host run{" "}
                  <code>chown -R 99:100 /mnt/user/data/media/library/books</code> (match the container PUID/PGID),
                  then Apply again. Do not chmod 777.
                </>
              )}
            </p>
            {shelfHealth.chown_command ? (
              <p className="muted">
                Copy-paste: <code data-testid="maintain-shelf-health-chown-cmd">{shelfHealth.chown_command}</code>
              </p>
            ) : null}
          </div>
        ) : null}
        {shelfHealthError ? <p className="alert">{shelfHealthError}</p> : null}
        <div className="cta-row">
          <button
            type="button"
            className="cta outline"
            disabled={scanning}
            aria-busy={scanning || undefined}
            onClick={startScanShelves}
            data-testid="maintain-scan"
          >
            {scanning ? busyLabel("scan") : "Scan the shelves"}
          </button>
          <button
            type="button"
            className="cta outline"
            disabled={enriching}
            aria-busy={enriching || undefined}
            onClick={startEnrichShelves}
            data-testid="maintain-enrich"
          >
            {enriching ? busyLabel("enrich") : "Enrich the shelves"}
          </button>
          <button
            type="button"
            className="cta outline"
            disabled={suggesting}
            onClick={async () => {
              setSuggestNote("");
              setSuggesting(true);
              try {
                const data = await api.refreshSuggestCache(false);
                const counts = data.counts || {};
                const total = Object.values(counts).reduce((sum, n) => sum + Number(n || 0), 0);
                setSuggestNote(`Suggestions refreshed · ${total} labels from the shelves`);
              } catch (err) {
                setSuggestNote(humanError(err));
              } finally {
                setSuggesting(false);
              }
            }}
            data-testid="maintain-suggest"
          >
            {suggesting ? "Refreshing…" : "Refresh suggestions"}
          </button>
        </div>
        {scan ? <p className="muted">{scan}</p> : null}
        {enrich ? <p className="muted">{enrich}</p> : null}
        {suggestNote ? <p className={/^Suggestions /.test(suggestNote) ? "muted" : "alert"}>{suggestNote}</p> : null}
        {scanStatus && scanning ? (
          <p className="sr-only" data-testid="maintain-scan-running">
            Scan running
          </p>
        ) : null}
        {enrichStatus && enriching ? (
          <p className="sr-only" data-testid="maintain-enrich-running">
            Enrich running
          </p>
        ) : null}
      </section>

      <section className="maintain-section" data-testid="maintain-goodreads">
        <p className="kicker">Goodreads</p>
        <h2>Import a shelf CSV</h2>
        <p className="lede">
          Export a shelf from Goodreads and match by ISBN onto Favorites. Rows without an ISBN are skipped.
        </p>
        <div className="field">
          <FieldLabel htmlFor="maintain-goodreads-csv" label="Shelf export" help={FIELD_HELP.goodreads_csv} />
          <input
            id="maintain-goodreads-csv"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
          />
        </div>
        <div className="cta-row">
          <button
            type="button"
            className="cta outline"
            disabled={importing || !csvFile}
            onClick={async () => {
              if (!csvFile) return;
              setGoodreads("");
              setImporting(true);
              try {
                const data = await api.importGoodreads(csvFile);
                setGoodreads(
                  `Imported ${data.rows} rows · ${data.matched} matched · ${data.created} new · ${data.favorited} favorited · ${data.skipped} skipped`,
                );
              } catch (err) {
                setGoodreads(humanError(err));
              } finally {
                setImporting(false);
              }
            }}
            data-testid="maintain-goodreads-import"
          >
            {importing ? "Importing…" : "Import Goodreads CSV"}
          </button>
        </div>
        {goodreads ? <p className={/^Imported /.test(goodreads) ? "muted" : "alert"}>{goodreads}</p> : null}
      </section>
    </div>
  );
}
