import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { busyLabel, doneLabel, ticketStatusNote } from "../actionBusy.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import { FIELD_HELP, emptyReviewCopy, humanError } from "../copy.js";
import { requestBodyFromHit } from "../find.js";
import SearchTraceDisclosure from "../components/SearchTraceDisclosure.jsx";
import {
  applyBodyFromDraft,
  applySuggestionToDraft,
  collisionActionCopy,
  collisionApplyAllowed,
  effectiveReviewReason,
  extraFilesReprocessIsRunning,
  extraFilesReprocessProgressPercent,
  extraFilesReprocessProgressSummary,
  fieldsFromWork,
  looksLikeDumpTitle,
  reviewActionsFromWork,
  reviewBulkClearVisible,
  reviewBulkRowVisible,
  reviewDiagnosisCopy,
  reviewExtraFilesProgressVisible,
  reviewFindHref,
  reviewReasonCopy,
  extraFilesWorks,
  unpackStuckWorks,
} from "../review.js";

const KINDS = ["book", "magazine", "comic", "audiobook", "music"];

export default function ReviewPage() {
  const [params] = useSearchParams();
  const focusId = String(params.get("work") || "").trim();
  const [works, setWorks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState({});
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState({});
  const [actionNotes, setActionNotes] = useState({});
  const [bulkNote, setBulkNote] = useState("");
  const [extraFilesProgress, setExtraFilesProgress] = useState(null);
  const [extraFilesClearing, setExtraFilesClearing] = useState(false);
  const [extraFilesBacklog, setExtraFilesBacklog] = useState(0);
  const [error, setError] = useState("");
  const [regrabs, setRegrabs] = useState({});
  const [matchBags, setMatchBags] = useState({});
  const [quiet, setQuiet] = useState(null);
  const [quietNote, setQuietNote] = useState("");
  const [suggestNotes, setSuggestNotes] = useState({});
  const focusRef = useRef(null);
  const extraFilesPollRef = useRef(0);
  const autoRegrabTried = useRef(new Set());
  const autoMatchTried = useRef(new Set());
  const autoSuggestTried = useRef(new Set());

  function reload() {
    api
      .review()
      .then((data) => {
        const next = data.works || [];
        setWorks(next);
        if (data.extra_files_count != null) {
          setExtraFilesBacklog(Number(data.extra_files_count) || 0);
        }
        setDrafts((prev) => {
          const merged = { ...prev };
          next.forEach((work) => {
            const base = fieldsFromWork(work);
            const suggested = work.folder_diagnosis?.suggested_folder;
            if (!merged[work.id]) {
              merged[work.id] = {
                ...base,
                folder: base.folder || suggested || "",
              };
            }
          });
          return merged;
        });
      })
      .catch((err) => setError(humanError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  useEffect(() => {
    api
      .quietHours()
      .then(setQuiet)
      .catch(() => setQuiet(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .reviewReprocessExtraFilesStatus()
      .then((status) => {
        if (cancelled) return;
        setExtraFilesProgress(status);
        if (status?.extra_files_remaining != null) {
          setExtraFilesBacklog(Number(status.extra_files_remaining) || 0);
        }
        if (extraFilesReprocessIsRunning(status)) {
          setExtraFilesClearing(true);
          setBulkNote(extraFilesReprocessProgressSummary(status) || "Clearing extra-files…");
        } else if (status?.status === "completed" || status?.status === "failed") {
          const summary = extraFilesReprocessProgressSummary(status);
          if (summary) setBulkNote(summary);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!extraFilesClearing) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const status = await api.reviewReprocessExtraFilesStatus();
        if (cancelled) return;
        setExtraFilesProgress(status);
        if (status?.extra_files_remaining != null) {
          setExtraFilesBacklog(Number(status.extra_files_remaining) || 0);
        }
        const summary = extraFilesReprocessProgressSummary(status);
        if (summary) setBulkNote(summary);
        if (extraFilesReprocessIsRunning(status)) {
          extraFilesPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setExtraFilesClearing(false);
        if (status?.status === "failed") {
          setBulkNote(status.error || "Clear extra-files failed.");
        } else if (status?.status === "completed") {
          setBulkNote(summary || "Finished clearing extra-files slips.");
          reload();
        }
      } catch (err) {
        if (cancelled) return;
        setExtraFilesClearing(false);
        setBulkNote(humanError(err));
      }
    }

    extraFilesPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(extraFilesPollRef.current);
    };
  }, [extraFilesClearing]);

  useEffect(() => {
    if (!focusId || !works.length) return;
    focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, works]);

  async function saveQuiet(patch) {
    setQuietNote("");
    try {
      const next = await api.saveQuietHours({ ...(quiet || {}), ...patch });
      setQuiet(next);
      setQuietNote("Quiet hours saved.");
    } catch (err) {
      setQuietNote(humanError(err));
    }
  }

  function patch(workId, key, value) {
    setDrafts((prev) => ({
      ...prev,
      [workId]: { ...(prev[workId] || {}), [key]: value },
    }));
  }

  function setWorkBusy(workId, action) {
    setBusy((prev) => {
      const next = { ...prev };
      if (action) next[workId] = action;
      else delete next[workId];
      return next;
    });
  }

  function setTicketNote(workId, note) {
    setActionNotes((prev) => ({ ...prev, [workId]: note || "" }));
  }

  async function runTicketAction(work, action, runner, { successNote } = {}) {
    if (busy[work.id]) return;
    setWorkBusy(work.id, action);
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    setTicketNote(work.id, busyLabel(action));
    try {
      await runner();
      setTicketNote(work.id, successNote || doneLabel(action));
    } catch (err) {
      const message = humanError(err);
      setErrors((prev) => ({ ...prev, [work.id]: message }));
      setTicketNote(work.id, message);
      throw err;
    } finally {
      setWorkBusy(work.id, "");
    }
  }

  async function apply(work) {
    try {
      await runTicketAction(work, "apply", async () => {
        await api.reviewApply(work.id, applyBodyFromDraft(drafts[work.id] || fieldsFromWork(work)));
        setDrafts((prev) => {
          const next = { ...prev };
          delete next[work.id];
          return next;
        });
        reload();
      });
    } catch {
      /* note already set */
    }
  }

  async function skip(work) {
    try {
      await runTicketAction(work, "skip", async () => {
        await api.reviewSkip(work.id);
        setDrafts((prev) => {
          const next = { ...prev };
          delete next[work.id];
          return next;
        });
        reload();
      });
    } catch {
      /* note already set */
    }
  }

  async function repair(work) {
    try {
      await runTicketAction(work, "repair", async () => {
        await api.reviewRepair(work.id);
        reload();
      });
    } catch {
      /* note already set */
    }
  }

  async function retry(work) {
    try {
      await runTicketAction(work, "retry", async () => {
        await api.reviewRetry(work.id);
        reload();
      });
    } catch {
      /* note already set */
    }
  }

  async function loadRegrab(work) {
    try {
      await runTicketAction(work, "regrab", async () => {
        const data = await api.reviewRegrab(work.id);
        setRegrabs((prev) => ({ ...prev, [work.id]: data }));
      });
    } catch {
      /* note already set */
    }
  }

  async function loadAuthorityMatches(work) {
    try {
      await runTicketAction(work, "match", async () => {
        const data = await api.matchCandidates(work.id);
        setMatchBags((prev) => ({ ...prev, [work.id]: data }));
      });
    } catch {
      /* note already set */
    }
  }

  async function applyAuthorityMatch(work, candidate) {
    const key = candidate?.match_key || candidate?.asin || "";
    if (!key) return;
    try {
      await runTicketAction(work, "applyMatch", async () => {
        await api.applyMatch(work.id, key);
        setMatchBags((prev) => {
          const next = { ...prev };
          delete next[work.id];
          return next;
        });
        reload();
      }, { successNote: "Match applied." });
    } catch {
      /* note already set */
    }
  }

  useEffect(() => {
    for (const work of works) {
      const reason = effectiveReviewReason(work);
      if (!String(reason || "").match(/^(audnexus|comicvine)_/)) continue;
      if (matchBags[work.id]) continue;
      if (autoMatchTried.current.has(work.id)) continue;
      autoMatchTried.current.add(work.id);
      loadAuthorityMatches(work);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [works]);

  useEffect(() => {
    for (const work of works) {
      const actions = reviewActionsFromWork(work);
      if (!actions.canRegrab) continue;
      if (autoRegrabTried.current.has(work.id)) continue;
      if (regrabs[work.id]) continue;
      autoRegrabTried.current.add(work.id);
      loadRegrab(work);
    }
    // Auto-fetch once per slip when can_regrab; manual Smart re-grab still refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [works]);

  async function suggestWithLlm(work, { silent = false } = {}) {
    if (busy[work.id]) return;
    setWorkBusy(work.id, "suggest");
    if (!silent) setErrors((prev) => ({ ...prev, [work.id]: "" }));
    setSuggestNotes((prev) => ({ ...prev, [work.id]: silent ? "" : busyLabel("suggest") }));
    setTicketNote(work.id, silent ? "" : busyLabel("suggest"));
    try {
      const data = await api.reviewSuggest(work.id);
      if (data?.suggestion) {
        setDrafts((prev) => ({
          ...prev,
          [work.id]: applySuggestionToDraft(prev[work.id] || fieldsFromWork(work), data.suggestion),
        }));
        const note = data.note || doneLabel("suggest");
        setSuggestNotes((prev) => ({ ...prev, [work.id]: note }));
        setTicketNote(work.id, note);
      } else {
        const note = data?.note || "No suggestion returned.";
        setSuggestNotes((prev) => ({ ...prev, [work.id]: note }));
        setTicketNote(work.id, note);
      }
    } catch (err) {
      if (!silent) setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
      const message = humanError(err);
      setSuggestNotes((prev) => ({ ...prev, [work.id]: message }));
      setTicketNote(work.id, message);
    } finally {
      setWorkBusy(work.id, "");
    }
  }

  useEffect(() => {
    for (const work of works) {
      const actions = reviewActionsFromWork(work);
      if (!actions.canSuggestLlm && !actions.needsLlmSuggest) continue;
      if (!actions.llmConfigured) continue;
      if (autoSuggestTried.current.has(work.id)) continue;
      const draft = drafts[work.id] || fieldsFromWork(work);
      if (!looksLikeDumpTitle(draft.title) && draft.author) continue;
      if (!actions.needsLlmSuggest && !looksLikeDumpTitle(draft.title)) continue;
      autoSuggestTried.current.add(work.id);
      suggestWithLlm(work, { silent: true });
    }
    // Auto-suggest once for dump-looking slips so the form is not pre-filled with junk.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [works, drafts]);

  async function requestRegrab(work, candidate) {
    try {
      await runTicketAction(work, "request", async () => {
        const bag = regrabs[work.id] || {};
        const candidates = bag.remembered_candidates || bag.candidates || [];
        await api.requestItem(
          requestBodyFromHit(
            candidate,
            {
              kind: work.kind || candidate.kind || "",
              title: work.title || "",
              author: work.author || "",
            },
            {
              candidates,
              rank_method: bag.rank_method || "",
              rank_reason: bag.rank_reason || "",
            },
          ),
        );
        reload();
      });
    } catch {
      /* note already set */
    }
  }

  async function bulkAction(kind) {
    const stuck = unpackStuckWorks(works).filter((work) => {
      const actions = reviewActionsFromWork(work);
      return kind === "repair" ? actions.canRepair : actions.canRetry;
    });
    if (!stuck.length) {
      setBulkNote(kind === "repair" ? "No slips with Repair available." : "No slips ready to Retry.");
      return;
    }
    setBulkNote(`${kind === "repair" ? "Repairing" : "Retrying"} ${stuck.length}…`);
    let ok = 0;
    for (const work of stuck) {
      try {
        if (kind === "repair") await api.reviewRepair(work.id);
        else await api.reviewRetry(work.id);
        ok += 1;
      } catch {
        /* continue */
      }
    }
    setBulkNote(`${ok} of ${stuck.length} ${kind === "repair" ? "repaired" : "retried"}.`);
    reload();
  }

  async function bulkReprocessExtraFiles() {
    if (extraFilesClearing) return;
    const visible = extraFilesWorks(works).length;
    const backlog = Math.max(visible, Number(extraFilesBacklog) || 0);
    if (!backlog) {
      setBulkNote("No extra_files slips to clear.");
      return;
    }
    setExtraFilesClearing(true);
    setExtraFilesProgress({
      status: "running",
      phase: "starting",
      done: 0,
      total: 0,
      shelved: 0,
      split: 0,
      applied: 0,
      failed: 0,
      extra_files_remaining: backlog,
    });
    setBulkNote(
      visible
        ? `Reprocessing extra_files (visible ${visible}; server clears the full backlog)…`
        : `Reprocessing extra_files backlog (${backlog})…`,
    );
    try {
      const started = await api.reviewReprocessExtraFiles();
      setExtraFilesProgress(started);
      if (started?.extra_files_remaining != null) {
        setExtraFilesBacklog(Number(started.extra_files_remaining) || 0);
      }
      setBulkNote(extraFilesReprocessProgressSummary(started) || "Clearing extra-files…");
      if (!extraFilesReprocessIsRunning(started) && started?.status === "completed") {
        setExtraFilesClearing(false);
        setBulkNote(extraFilesReprocessProgressSummary(started) || "Finished clearing extra-files slips.");
        reload();
      }
    } catch (err) {
      setExtraFilesClearing(false);
      setBulkNote(humanError(err));
    }
  }

  const unpackCount = unpackStuckWorks(works).length;
  const extraFilesCount = extraFilesWorks(works).length;
  const showExtraFilesProgress = reviewExtraFilesProgressVisible(extraFilesProgress, extraFilesClearing);
  const showBulkClear = reviewBulkClearVisible({
    visibleCount: extraFilesCount,
    backlogCount: extraFilesBacklog,
    clearing: extraFilesClearing,
    progress: extraFilesProgress,
  });
  const showBulkRow = reviewBulkRowVisible({
    unpackCount,
    showClear: showBulkClear,
    showProgress: showExtraFilesProgress,
  });
  const extraFilesPercent = showExtraFilesProgress
    ? extraFilesReprocessProgressPercent(extraFilesProgress)
    : null;

  return (
    <div className="admin-room">
      <p className="kicker">Bagging area</p>
      <h1>Review</h1>
      <p className="lede">
        Slips are downloads organize could not finish filing. Happy-path ISBN books never appear here. Apply files a
        ticket once the folder has readable media — Skip dismisses without shelving.
      </p>
      {quiet ? (
        <details className="more-settings" data-testid="review-quiet-hours">
          <summary className="kicker">Quiet hours</summary>
          <p className="muted">
            {quiet.active_now ? "Active now — new unpacks wait for tonight." : "Inactive — Organize runs normally."}
          </p>
          <div className="field field-check">
            <label>
              <input
                type="checkbox"
                checked={Boolean(quiet.quiet_hours_enabled)}
                onChange={(e) => saveQuiet({ quiet_hours_enabled: e.target.checked })}
              />
              Defer unpack / convert
            </label>
          </div>
          <div className="cta-row compact">
            <label className="field">
              <span className="sr-only">Starts</span>
              <input
                value={quiet.quiet_hours_start || "22:00"}
                onChange={(e) => setQuiet({ ...quiet, quiet_hours_start: e.target.value })}
                onBlur={() => saveQuiet({ quiet_hours_start: quiet.quiet_hours_start })}
              />
            </label>
            <label className="field">
              <span className="sr-only">Ends</span>
              <input
                value={quiet.quiet_hours_end || "07:00"}
                onChange={(e) => setQuiet({ ...quiet, quiet_hours_end: e.target.value })}
                onBlur={() => saveQuiet({ quiet_hours_end: quiet.quiet_hours_end })}
              />
            </label>
          </div>
          {quietNote ? <p className="muted">{quietNote}</p> : null}
        </details>
      ) : null}
      {error ? <p className="alert">{error}</p> : null}
      {showBulkRow ? (
        <div className="cta-row review-bulk" data-testid="review-bulk">
          {unpackCount ? (
            <>
              <button type="button" className="cta outline compact" onClick={() => bulkAction("repair")}>
                Repair unpack slips
              </button>
              <button type="button" className="cta outline compact" onClick={() => bulkAction("retry")}>
                Retry unpack slips
              </button>
            </>
          ) : null}
          {showBulkClear ? (
            <button
              type="button"
              className="cta compact"
              onClick={() => bulkReprocessExtraFiles()}
              disabled={extraFilesClearing}
              data-testid="review-bulk-extra-files"
            >
              {extraFilesClearing
                ? "Clearing…"
                : extraFilesBacklog > 0 && extraFilesCount === 0
                  ? `Clear extra-files slips (${extraFilesBacklog})`
                  : "Clear extra-files slips"}
            </button>
          ) : null}
          {bulkNote && !showExtraFilesProgress ? (
            <p className="muted" role="status">
              {bulkNote}
            </p>
          ) : null}
        </div>
      ) : null}
      {showExtraFilesProgress ? (
        <section
          className="ingest-progress review-extra-files-progress"
          data-testid="review-extra-files-progress"
          aria-live="polite"
        >
          <p className="kicker">Clear extra-files progress</p>
          <p className="muted">
            {extraFilesProgress.phase || "clearing"}
            {extraFilesProgress.total
              ? ` · ${extraFilesProgress.done || 0} of ${extraFilesProgress.total}`
              : extraFilesProgress.done
                ? ` · ${extraFilesProgress.done} done`
                : ""}
            {extraFilesPercent != null ? ` · ${extraFilesPercent}%` : ""}
            {extraFilesProgress.shelved ? ` · shelved ${extraFilesProgress.shelved}` : ""}
            {extraFilesProgress.split ? ` · split ${extraFilesProgress.split}` : ""}
            {extraFilesProgress.applied ? ` · applied ${extraFilesProgress.applied}` : ""}
            {extraFilesProgress.failed ? ` · failed ${extraFilesProgress.failed}` : ""}
          </p>
          {extraFilesPercent != null ? (
            <div
              className="ingest-progress-meter"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={extraFilesPercent}
              aria-label="Clear extra-files progress"
            >
              <span className="ingest-progress-meter-fill" style={{ width: `${extraFilesPercent}%` }} />
            </div>
          ) : null}
          {extraFilesProgress.current_title ? (
            <p className="lede ingest-progress-title">{extraFilesProgress.current_title}</p>
          ) : null}
          {bulkNote ? (
            <p className="muted" role="status">
              {bulkNote}
            </p>
          ) : null}
        </section>
      ) : null}
      {loading ? (
        <section className="review-loading" data-testid="review-loading" aria-busy="true">
          <p className="muted">Warming the lamp on the bagging area…</p>
          <div className="hall-shelves-skeleton" aria-hidden="true" />
        </section>
      ) : !works.length ? (
        <section className="empty-cta review-empty" data-testid="review-empty">
          <p className="empty-illustration" aria-hidden="true">
            <span className="empty-lamp" />
          </p>
          <p className="lede empty-note">{emptyReviewCopy()}</p>
        </section>
      ) : null}
      <ul className="stack">
        {works.map((work) => {
          const draft = drafts[work.id] || fieldsFromWork(work);
          const focused = Boolean(focusId) && work.id === focusId;
          const reason = effectiveReviewReason(work);
          const collision = reason === "collision";
          const canApply = collisionApplyAllowed(reason, draft, work);
          const shelf = work.shelf_work;
          const diagnosis = reviewDiagnosisCopy(work);
          const actions = reviewActionsFromWork(work);
          const findTo = reviewFindHref(work);
          const workBusy = Boolean(busy[work.id]);
          const activeAction = typeof busy[work.id] === "string" ? busy[work.id] : "";
          const statusNote = ticketStatusNote(busy, actionNotes, work.id) || suggestNotes[work.id] || "";
          return (
            <li
              key={work.id}
              ref={focused ? focusRef : null}
              className={["card", "ticket", "ticket-enter", focused ? "is-focus" : ""].filter(Boolean).join(" ")}
              data-testid="review-ticket"
              data-work-id={work.id}
              data-focused={focused ? "true" : "false"}
              data-reason={reason || ""}
              aria-busy={workBusy || undefined}
            >
              <header className="ticket-head">
                <p className="kicker">{focused ? "From Queue" : "Slip"}</p>
                <span className="seal">{draft.kind || work.kind}</span>
              </header>
              <strong className="ticket-title">{draft.title || work.title || "Untitled"}</strong>
              {actions.quietHours ? (
                <p className="chip is-on" data-testid="quiet-hours-chip">
                  Queued for tonight
                </p>
              ) : null}
              <p className="lede" data-testid="review-reason-copy">
                {reviewReasonCopy(reason)}
              </p>
              <details className="ticket-diagnosis" data-testid="review-diagnosis">
                <summary>About this slip</summary>
                <div className="empty-note">
                  <p>
                    <strong>What this slip means.</strong> {diagnosis.meaning}
                  </p>
                  <p>
                    <strong>What we tried.</strong> {diagnosis.tried}
                  </p>
                  <p>
                    <strong>What’s wrong.</strong> {diagnosis.whatsWrong}
                  </p>
                  <p>
                    <strong>What to do.</strong> {diagnosis.nextSteps}
                  </p>
                  {diagnosis.pathNote ? (
                    <p data-testid="review-path-note">
                      <strong>About this path.</strong> {diagnosis.pathNote}
                    </p>
                  ) : null}
                  {diagnosis.suggestedFolder ? (
                    <p data-testid="review-suggested-folder">
                      <strong>Suggested folder.</strong>{" "}
                      <code className="font-mono">{diagnosis.suggestedFolder}</code>{" "}
                      <button
                        type="button"
                        className="cta ghost compact"
                        onClick={() => patch(work.id, "folder", diagnosis.suggestedFolder)}
                      >
                        Use this path
                      </button>
                    </p>
                  ) : null}
                </div>
              </details>
              {collision ? (
                <p className="empty-note" data-testid="collision-action-copy">
                  {collisionActionCopy()}
                </p>
              ) : null}
              {shelf?.id ? (
                <p className="muted" data-testid="collision-shelf-link">
                  Already cataloged:{" "}
                  <Link to={`/works/${encodeURIComponent(shelf.id)}`}>
                    {shelf.title || "Open on Hall"}
                    {shelf.author ? ` — ${shelf.author}` : ""}
                  </Link>
                </p>
              ) : null}
              {Array.isArray(work.match_candidates) && work.match_candidates.length ? (
                <div className="match-candidates" data-testid="review-match-candidates">
                  <p className="kicker">Match candidates</p>
                  <ul className="match-candidate-list">
                    {work.match_candidates.map((row) => (
                      <li key={row.match_key || `${row.title}-${row.series_name}`}>
                        <div>
                          <strong>{row.title || row.series_name}</strong>
                          <span className="muted">
                            {[
                              row.series_name,
                              row.series_index ? `#${row.series_index}` : "",
                              row.volume_year || row.year,
                              row.publisher,
                              row.match_confidence != null
                                ? `${Math.round(Number(row.match_confidence) * 100)}%`
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="cta outline compact"
                          disabled={workBusy}
                          data-testid="review-apply-match"
                          onClick={async () => {
                            setWorkBusy(work.id, "match");
                            setErrors((prev) => ({ ...prev, [work.id]: "" }));
                            try {
                              const result = await api.applyMatch(work.id, row.match_key);
                              const next = result?.work || {};
                              setDrafts((prev) => ({
                                ...prev,
                                [work.id]: applySuggestionToDraft(prev[work.id] || fieldsFromWork(work), {
                                  title: next.title,
                                  author: next.author,
                                  series_name: next.series_name,
                                  series_index: next.series_index,
                                  year: next.year,
                                  kind: "comic",
                                }),
                              }));
                              setTicketNote(work.id, "Match applied — confirm folder and Apply to file.");
                              reload();
                            } catch (err) {
                              setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
                            } finally {
                              setWorkBusy(work.id, "");
                            }
                          }}
                        >
                          Use this
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {(actions.canRepair ||
                actions.canRetry ||
                actions.canRequestNew ||
                actions.canRegrab ||
                actions.canSuggestLlm) && (
                <div className="cta-row ticket-recovery" data-testid="review-recovery">
                  {actions.canSuggestLlm ? (
                    <button
                      type="button"
                      className="cta outline compact"
                      disabled={workBusy}
                      aria-busy={activeAction === "suggest" || undefined}
                      onClick={() => suggestWithLlm(work)}
                      data-testid="review-suggest-llm"
                    >
                      {activeAction === "suggest" ? busyLabel("suggest") : "Suggest with LLM"}
                    </button>
                  ) : null}
                  {actions.canRepair ? (
                    <button
                      type="button"
                      className="cta compact"
                      disabled={workBusy}
                      aria-busy={activeAction === "repair" || undefined}
                      onClick={() => repair(work)}
                      data-testid="review-repair"
                    >
                      {activeAction === "repair" ? busyLabel("repair") : "Repair"}
                    </button>
                  ) : null}
                  {actions.canRetry ? (
                    <button
                      type="button"
                      className={`cta compact${actions.canRepair ? " outline" : ""}`}
                      disabled={workBusy}
                      aria-busy={activeAction === "retry" || undefined}
                      onClick={() => retry(work)}
                      data-testid="review-retry"
                    >
                      {activeAction === "retry" ? busyLabel("retry") : "Retry"}
                    </button>
                  ) : null}
                  {actions.canRegrab ? (
                    <button
                      type="button"
                      className="cta outline compact"
                      disabled={workBusy}
                      aria-busy={activeAction === "regrab" || undefined}
                      onClick={() => loadRegrab(work)}
                      data-testid="review-regrab"
                    >
                      {activeAction === "regrab" ? busyLabel("regrab") : "Smart re-grab"}
                    </button>
                  ) : null}
                  {actions.canRequestNew ? (
                    <Link
                      className="cta outline compact"
                      to={findTo}
                      data-testid="review-request-new"
                    >
                      Request new version
                    </Link>
                  ) : null}
                </div>
              )}
              {statusNote ? (
                <p className="muted" data-testid="review-action-note" role="status">
                  {statusNote}
                </p>
              ) : null}
              {matchBags[work.id]?.candidates?.length ? (
                <ul className="regrab-list" data-testid="authority-match-candidates">
                  {matchBags[work.id].candidates.map((candidate, index) => (
                    <li key={candidate.match_key || candidate.asin || candidate.title || index}>
                      <span>
                        {candidate.title || "Untitled"}
                        {candidate.author ? ` — ${candidate.author}` : ""}
                        {candidate.asin ? ` · ${candidate.asin}` : ""}
                        {candidate.score != null || candidate.match_confidence != null
                          ? ` · ${Math.round(Number(candidate.score ?? candidate.match_confidence) * 100)}%`
                          : ""}
                      </span>
                      <button
                        type="button"
                        className={index === 0 ? "cta compact" : "cta compact outline"}
                        disabled={workBusy}
                        aria-busy={activeAction === "applyMatch" || undefined}
                        onClick={() => applyAuthorityMatch(work, candidate)}
                        data-testid="authority-match-apply"
                      >
                        {activeAction === "applyMatch" ? busyLabel("applyMatch") : "Use this match"}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {regrabs[work.id]?.beyond_error ? (
                <p className="muted" role="status" data-testid="regrab-beyond-error">
                  {humanError(regrabs[work.id].beyond_error)}
                </p>
              ) : null}
              {regrabs[work.id]?.search_trace || regrabs[work.id]?.remembered_candidates?.length ? (
                <SearchTraceDisclosure
                  conversation={regrabs[work.id]?.search_trace?.conversation || []}
                  steps={regrabs[work.id]?.search_trace?.steps || []}
                  results={regrabs[work.id]?.search_trace?.results || []}
                  candidates={regrabs[work.id]?.remembered_candidates || regrabs[work.id]?.candidates || []}
                  rankMethod={regrabs[work.id]?.rank_method || ""}
                  rankReason={regrabs[work.id]?.rank_reason || ""}
                  testId={`regrab-trace-${work.id}`}
                />
              ) : null}
              {regrabs[work.id]?.candidates?.length ? (
                <ul className="regrab-list" data-testid="regrab-candidates">
                  {regrabs[work.id].candidates.map((candidate, index) => (
                    <li key={candidate.guid || candidate.title}>
                      <span>{candidate.diff || candidate.title}</span>
                      <button
                        type="button"
                        className={index === 0 ? "cta compact" : "cta compact outline"}
                        disabled={workBusy}
                        aria-busy={activeAction === "request" || undefined}
                        onClick={() => requestRegrab(work, candidate)}
                        data-testid="regrab-request"
                      >
                        {activeAction === "request" ? busyLabel("request") : "Request this"}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : regrabs[work.id]?.ready && !regrabs[work.id]?.candidates?.length ? (
                <p className="muted" data-testid="regrab-empty">
                  No alternate releases yet — try Request new version on Find.
                </p>
              ) : null}
              <form
                className="identify-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!canApply) return;
                  apply(work);
                }}
              >
                <div className="field">
                  <FieldLabel htmlFor={`kind-${work.id}`} label="Kind" help={FIELD_HELP.reviewKind} />
                  <select
                    id={`kind-${work.id}`}
                    value={draft.kind}
                    onChange={(e) => patch(work.id, "kind", e.target.value)}
                  >
                    {KINDS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`title-${work.id}`} label="Title" help={FIELD_HELP.reviewTitle} />
                  <input
                    id={`title-${work.id}`}
                    value={draft.title}
                    onChange={(e) => patch(work.id, "title", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`author-${work.id}`} label="Author" help={FIELD_HELP.reviewAuthor} />
                  <input
                    id={`author-${work.id}`}
                    value={draft.author}
                    onChange={(e) => patch(work.id, "author", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`isbn-${work.id}`} label="ISBN" help={FIELD_HELP.reviewIsbn} />
                  <input
                    id={`isbn-${work.id}`}
                    className="font-mono"
                    value={draft.isbn}
                    onChange={(e) => patch(work.id, "isbn", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`series-${work.id}`} label="Series" help={FIELD_HELP.reviewSeries} />
                  <input
                    id={`series-${work.id}`}
                    value={draft.series_name}
                    onChange={(e) => patch(work.id, "series_name", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`index-${work.id}`} label="Issue / index" help={FIELD_HELP.reviewIndex} />
                  <input
                    id={`index-${work.id}`}
                    value={draft.series_index}
                    onChange={(e) => patch(work.id, "series_index", e.target.value)}
                  />
                </div>
                <div className="field field-wide">
                  <FieldLabel htmlFor={`folder-${work.id}`} label="Complete folder" help={FIELD_HELP.reviewFolder} />
                  <input
                    id={`folder-${work.id}`}
                    value={draft.folder}
                    onChange={(e) => patch(work.id, "folder", e.target.value)}
                    placeholder="Path this Librarian process can read"
                  />
                </div>
                {errors[work.id] ? <p className="alert field-wide">{errors[work.id]}</p> : null}
                <div className="cta-row field-wide">
                  <button
                    type="submit"
                    className="cta"
                    disabled={!canApply || workBusy}
                    aria-busy={activeAction === "apply" || undefined}
                    title={
                      collision && !canApply
                        ? "Change title, author, series, or folder so the destination is free — Apply will not overwrite."
                        : undefined
                    }
                    data-testid="review-apply"
                  >
                    {activeAction === "apply" ? busyLabel("apply") : "Apply"}
                  </button>
                  <button
                    type="button"
                    className="cta ghost"
                    disabled={workBusy}
                    aria-busy={activeAction === "skip" || undefined}
                    onClick={() => skip(work)}
                    data-testid="review-skip"
                  >
                    {activeAction === "skip" ? busyLabel("skip") : "Skip"}
                  </button>
                </div>
              </form>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
