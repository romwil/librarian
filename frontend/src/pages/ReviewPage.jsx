import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { busyLabel, doneLabel, ticketStatusNote } from "../actionBusy.js";
import HoldSlipCard from "../components/HoldSlipCard.jsx";
import HoldsGroupActions from "../components/HoldsGroupActions.jsx";
import JobProgress from "../components/JobProgress.jsx";
import ReviewBulkBar from "../components/ReviewBulkBar.jsx";
import { emptyReviewCopy, humanError } from "../copy.js";
import { requestBodyFromHit } from "../find.js";
import { useProgressJob } from "../hooks/useProgressJob.js";
import {
  applyBodyFromDraft,
  applySuggestionToDraft,
  badReleaseMigrationSummary,
  badReleaseMigrationVisible,
  bulkResultSummary,
  effectiveReviewReason,
  extraFilesReprocessIsRunning,
  extraFilesReprocessProgressPercent,
  extraFilesReprocessProgressSummary,
  fieldsFromWork,
  groupHoldSlipsByReason,
  holdsDeskLedeCopy,
  looksLikeDumpTitle,
  purgeDuplicatesIsRunning,
  purgeDuplicatesProgressPercent,
  purgeDuplicatesProgressSummary,
  recommendedMotionLabel,
  reviewActionsFromWork,
  reviewBulkClearVisible,
  reviewBulkPurgeVisible,
  reviewBulkRowVisible,
  reviewExtraFilesProgressVisible,
  reviewProgressDwellRemainingMs,
  reviewPurgeProgressVisible,
  slipTriage,
  suggestBatchIsRunning,
  suggestBatchSummary,
  triageCountsFromWorks,
  extraFilesWorks,
  unpackStuckWorks,
} from "../review.js";

function migrationIsRunning(status) {
  return String(status?.status || "") === "running";
}

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
  const [groupNote, setGroupNote] = useState("");
  const [modelNote, setModelNote] = useState("");
  const [applyingTrusted, setApplyingTrusted] = useState(false);
  const [migration, setMigration] = useState(null);
  const lastTriageDone = useRef(-1);
  const [extraFilesBacklog, setExtraFilesBacklog] = useState(0);
  const [progressClock, setProgressClock] = useState(() => Date.now());
  const [reviewBacklog, setReviewBacklog] = useState(0);
  const [error, setError] = useState("");
  const [regrabs, setRegrabs] = useState({});
  const [matchBags, setMatchBags] = useState({});
  const [quiet, setQuiet] = useState(null);
  const [quietNote, setQuietNote] = useState("");
  const [suggestNotes, setSuggestNotes] = useState({});
  const [ownedSlipNote, setOwnedSlipNote] = useState("");
  const focusRef = useRef(null);
  const autoMatchTried = useRef(new Set());
  const autoSuggestTried = useRef(new Set());
  const triageSeeded = useRef(new Set());
  const reloadRef = useRef(() => {});

  function reload() {
    api
      .review(focusId)
      .then((data) => {
        const next = data.works || [];
        setWorks(next);
        if (data.extra_files_count != null) {
          setExtraFilesBacklog(Number(data.extra_files_count) || 0);
        }
        if (data.needs_review_count != null) {
          setReviewBacklog(Number(data.needs_review_count) || 0);
        } else {
          setReviewBacklog(next.length);
        }
        setOwnedSlipNote(String(data.owned_slip_note || "").trim());
        if (data.bad_release_migration) setMigration(data.bad_release_migration);
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
            const triaged = slipTriage(work)?.suggestion;
            const seedKey = `${work.id}:${slipTriage(work)?.outcome || ""}`;
            if (triaged && !triageSeeded.current.has(seedKey)) {
              triageSeeded.current.add(seedKey);
              merged[work.id] = applySuggestionToDraft(merged[work.id], triaged);
            }
          });
          return merged;
        });
      })
      .catch((err) => setError(humanError(err)))
      .finally(() => setLoading(false));
  }
  reloadRef.current = reload;

  useEffect(reload, [focusId]);

  useEffect(() => {
    api
      .quietHours()
      .then(setQuiet)
      .catch(() => setQuiet(null));
  }, []);

  const fetchExtraStatus = useCallback(() => api.reviewReprocessExtraFilesStatus(), []);
  const fetchPurgeStatus = useCallback(() => api.reviewPurgeDuplicatesStatus(), []);

  const {
    status: extraFilesProgress,
    setStatus: setExtraFilesProgress,
    running: extraFilesClearing,
    setRunning: setExtraFilesClearing,
  } = useProgressJob({
    fetchStatus: fetchExtraStatus,
    isRunning: extraFilesReprocessIsRunning,
    pollIdle: true,
    onUpdate: (status) => {
      if (status?.extra_files_remaining != null) {
        setExtraFilesBacklog(Number(status.extra_files_remaining) || 0);
      }
      const summary = extraFilesReprocessProgressSummary(status);
      if (
        summary &&
        (extraFilesReprocessIsRunning(status) || status?.status === "completed" || status?.status === "failed")
      ) {
        setBulkNote(summary);
      }
    },
    onSettled: (status) => {
      if (status?.status === "failed") {
        setBulkNote(status.error || "Clear extra-files failed.");
      } else if (status?.status === "completed") {
        setBulkNote(extraFilesReprocessProgressSummary(status) || "Finished clearing extra-files slips.");
        reloadRef.current();
      }
    },
  });

  const {
    status: purgeProgress,
    setStatus: setPurgeProgress,
    running: purgeRunning,
    setRunning: setPurgeRunning,
  } = useProgressJob({
    fetchStatus: fetchPurgeStatus,
    isRunning: purgeDuplicatesIsRunning,
    pollIdle: true,
    onUpdate: (status) => {
      if (status?.needs_review_remaining != null) {
        setReviewBacklog(Number(status.needs_review_remaining) || 0);
      }
      const summary = purgeDuplicatesProgressSummary(status);
      if (
        summary &&
        (purgeDuplicatesIsRunning(status) || status?.status === "completed" || status?.status === "failed")
      ) {
        setBulkNote(summary);
      }
    },
    onSettled: (status) => {
      if (status?.status === "failed") {
        setBulkNote(status.error || "Purge duplicates failed.");
      } else if (status?.status === "completed") {
        setBulkNote(purgeDuplicatesProgressSummary(status) || "Finished purging duplicates.");
        reloadRef.current();
      }
    },
  });

  const fetchTriageStatus = useCallback(() => api.reviewSuggestBatchStatus(), []);
  const [triageKicked, setTriageKicked] = useState(false);
  const {
    status: triageProgress,
    setStatus: setTriageProgress,
    running: triageRunning,
    setRunning: setTriageRunning,
  } = useProgressJob({
    fetchStatus: fetchTriageStatus,
    isRunning: suggestBatchIsRunning,
    active: triageKicked,
    probe: true,
    liveMs: 1500,
    onUpdate: (status) => {
      if (!suggestBatchIsRunning(status)) {
        if (triageKicked && status?.status && status.status !== "idle") {
          setTriageKicked(false);
          reloadRef.current();
        }
        return;
      }
      const done = Number(status?.done || 0);
      if (done !== lastTriageDone.current) {
        lastTriageDone.current = done;
        reloadRef.current();
      }
    },
    onSettled: () => {
      lastTriageDone.current = -1;
      setTriageKicked(false);
      reloadRef.current();
    },
  });

  const fetchMigrationStatus = useCallback(() => api.reviewBadReleaseMigrationStatus(), []);
  useProgressJob({
    fetchStatus: fetchMigrationStatus,
    isRunning: migrationIsRunning,
    probe: true,
    liveMs: 1500,
    onUpdate: (status) => {
      if (status) setMigration(status);
    },
    onSettled: () => reloadRef.current(),
  });

  useEffect(() => {
    if (!focusId || !works.length) return;
    focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, works]);

  // Re-render when a completed Clear/Purge meter should drop off after its dwell.
  useEffect(() => {
    const now = Date.now();
    const remaining = [
      reviewProgressDwellRemainingMs(extraFilesProgress, { now }),
      reviewProgressDwellRemainingMs(purgeProgress, { now }),
    ].filter((ms) => ms != null && ms > 0);
    if (!remaining.length) return undefined;
    const wait = Math.min(...remaining) + 50;
    const timer = window.setTimeout(() => setProgressClock(Date.now()), wait);
    return () => window.clearTimeout(timer);
  }, [extraFilesProgress, purgeProgress, progressClock]);

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
      const returned = await runner();
      const noted = returned && typeof returned.note === "string" ? returned.note : "";
      setTicketNote(work.id, noted || successNote || doneLabel(action));
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

  async function retrieveRelease(work, intent) {
    const action = intent === "new_version" ? "requestNew" : "regrab";
    try {
      await runTicketAction(work, action, async () => {
        const data = await api.reviewRetrieve(work.id, intent);
        setRegrabs((prev) => ({ ...prev, [work.id]: data }));
        if (data?.sab_error) throw new Error(data.sab_error);
        return { note: data?.note || "" };
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
      await runTicketAction(
        work,
        "applyMatch",
        async () => {
          await api.applyMatch(work.id, key);
          setMatchBags((prev) => {
            const next = { ...prev };
            delete next[work.id];
            return next;
          });
          reload();
        },
        { successNote: "Match applied." },
      );
    } catch {
      /* note already set */
    }
  }

  async function applyListedMatch(work, row) {
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
    if (triageRunning) return;
    for (const work of works) {
      const actions = reviewActionsFromWork(work);
      if (!actions.canSuggestLlm && !actions.needsLlmSuggest) continue;
      if (!actions.llmConfigured) continue;
      if (autoSuggestTried.current.has(work.id)) continue;
      if (slipTriage(work)) continue;
      const draft = drafts[work.id] || fieldsFromWork(work);
      if (!looksLikeDumpTitle(draft.title) && draft.author) continue;
      if (!actions.needsLlmSuggest && !looksLikeDumpTitle(draft.title)) continue;
      autoSuggestTried.current.add(work.id);
      suggestWithLlm(work, { silent: true });
    }
    // Auto-suggest once for dump-looking slips so the form is not pre-filled with junk.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [works, drafts, triageRunning]);

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

  function onGroupChanged(result) {
    setGroupNote(bulkResultSummary(result));
    reload();
  }

  function lowConfidenceSlips() {
    return works.filter((work) => {
      const actions = reviewActionsFromWork(work);
      const settled = ["trusted", "ambiguous"].includes(slipTriage(work)?.outcome || "");
      return (actions.canSuggestLlm || actions.needsLlmSuggest) && !settled;
    });
  }

  async function startModelTriage() {
    if (triageRunning) return;
    setModelNote("");
    setTriageRunning(true);
    try {
      const started = await api.reviewSuggestBatch();
      setTriageProgress(started);
      setTriageRunning(suggestBatchIsRunning(started));
      if (suggestBatchIsRunning(started)) setTriageKicked(true);
      else reload();
    } catch (err) {
      setTriageRunning(false);
      setModelNote(humanError(err));
    }
  }

  async function applyTrustedModelMatches() {
    if (applyingTrusted) return;
    setApplyingTrusted(true);
    setModelNote("");
    try {
      const result = await api.reviewApplyTrusted();
      const applied = Number(result?.applied || 0);
      const failed = Number(result?.failed || 0);
      setModelNote(
        `Filed ${applied} of ${Number(result?.examined || 0)} trusted matches.` +
          (failed ? ` ${failed} stayed on the desk (collision or moved folder).` : ""),
      );
      reload();
    } catch (err) {
      setModelNote(humanError(err));
    } finally {
      setApplyingTrusted(false);
    }
  }

  function runPrimary(work) {
    const motion = reviewActionsFromWork(work).recommendedMotion;
    if (motion === "repair") return repair(work);
    if (motion === "retry") return retry(work);
    if (motion === "regrab") return retrieveRelease(work, "regrab");
    if (motion === "request_new") return retrieveRelease(work, "new_version");
    if (motion === "skip") return skip(work);
    if (motion === "suggest") return suggestWithLlm(work);
    if (motion === "clear_extra_files") return bulkReprocessExtraFiles();
    if (motion === "wait") return undefined;
    return apply(work);
  }

  async function bulkPurgeDuplicates() {
    if (purgeRunning) return;
    const visible = works.length;
    const backlog = Math.max(visible, Number(reviewBacklog) || 0);
    if (!backlog) {
      setBulkNote("No Review slips to check for duplicates.");
      return;
    }
    setPurgeRunning(true);
    setPurgeProgress({
      status: "running",
      phase: "starting",
      done: 0,
      total: 0,
      purged: 0,
      shelf_twins: 0,
      slip_twins: 0,
      kept: 0,
      failed: 0,
      needs_review_remaining: backlog,
    });
    setBulkNote(
      visible
        ? `Purging duplicates (visible ${visible}; server checks the full Review backlog)…`
        : `Purging duplicates across Review backlog (${backlog})…`,
    );
    try {
      const started = await api.reviewPurgeDuplicates();
      setPurgeProgress(started);
      if (started?.needs_review_remaining != null) {
        setReviewBacklog(Number(started.needs_review_remaining) || 0);
      }
      setBulkNote(purgeDuplicatesProgressSummary(started) || "Purging duplicates…");
      if (!purgeDuplicatesIsRunning(started) && started?.status === "completed") {
        setPurgeRunning(false);
        setBulkNote(purgeDuplicatesProgressSummary(started) || "Finished purging duplicates.");
        reload();
      }
    } catch (err) {
      setPurgeRunning(false);
      setBulkNote(humanError(err));
    }
  }

  const unpackCount = unpackStuckWorks(works).length;
  const extraFilesCount = extraFilesWorks(works).length;
  const lowConfidenceCount = lowConfidenceSlips().length;
  const progressNow = progressClock;
  const showExtraFilesProgress = reviewExtraFilesProgressVisible(extraFilesProgress, extraFilesClearing, {
    now: progressNow,
  });
  const showPurgeProgress = reviewPurgeProgressVisible(purgeProgress, purgeRunning, {
    now: progressNow,
  });
  const showBulkClear = reviewBulkClearVisible({
    visibleCount: extraFilesCount,
    backlogCount: extraFilesBacklog,
    clearing: extraFilesClearing,
    progress: extraFilesProgress,
    now: progressNow,
  });
  const showBulkPurge = reviewBulkPurgeVisible({
    visibleCount: works.length,
    backlogCount: reviewBacklog,
    purging: purgeRunning,
    progress: purgeProgress,
    now: progressNow,
  });
  const triageCounts = triageCountsFromWorks(works);
  const trustedCount = triageCounts.trusted;
  const triageLine = suggestBatchSummary(triageProgress);
  const showMigration = badReleaseMigrationVisible(migration);
  const showBulkRow =
    lowConfidenceCount ||
    trustedCount ||
    triageRunning ||
    triageLine ||
    modelNote ||
    reviewBulkRowVisible({
      unpackCount,
      showClear: showBulkClear,
      showPurge: showBulkPurge,
      showProgress: showExtraFilesProgress || showPurgeProgress,
    });
  const extraFilesPercent = showExtraFilesProgress ? extraFilesReprocessProgressPercent(extraFilesProgress) : null;
  const purgePercent = showPurgeProgress ? purgeDuplicatesProgressPercent(purgeProgress) : null;
  const extraFilesStatusLine = showExtraFilesProgress ? extraFilesReprocessProgressSummary(extraFilesProgress) : "";
  const purgeStatusLine = showPurgeProgress ? purgeDuplicatesProgressSummary(purgeProgress) : "";
  const holdGroups = groupHoldSlipsByReason(works);

  return (
    <div className="admin-room review-page page-settle">
      <p className="kicker">Holds desk</p>
      <h1>Sorting returns</h1>
      <p className="lede">{holdsDeskLedeCopy()}</p>
      {ownedSlipNote ? (
        <p className="muted" role="status" data-testid="owned-slip-note">
          {ownedSlipNote}
        </p>
      ) : null}
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
      <ReviewBulkBar
        show={showBulkRow}
        unpackCount={unpackCount}
        onRepair={() => bulkAction("repair")}
        onRetry={() => bulkAction("retry")}
        showBulkClear={showBulkClear}
        extraFilesClearing={extraFilesClearing}
        extraFilesBacklog={extraFilesBacklog}
        extraFilesCount={extraFilesCount}
        onClearExtraFiles={bulkReprocessExtraFiles}
        showBulkPurge={showBulkPurge}
        purgeRunning={purgeRunning}
        reviewBacklog={reviewBacklog}
        slipCount={works.length}
        onPurgeDuplicates={bulkPurgeDuplicates}
        lowConfidenceCount={lowConfidenceCount}
        triageRunning={triageRunning}
        triageProgress={triageProgress}
        onStartTriage={startModelTriage}
        trustedCount={trustedCount}
        applyingTrusted={applyingTrusted}
        onApplyTrusted={applyTrustedModelMatches}
        triageLine={triageLine}
        triageCounts={triageCounts}
        modelNote={modelNote}
        bulkNote={bulkNote}
        showExtraFilesProgress={showExtraFilesProgress}
        showPurgeProgress={showPurgeProgress}
      />
      {showExtraFilesProgress ? (
        <JobProgress
          className="ingest-progress review-extra-files-progress"
          testId="review-extra-files-progress"
          kicker="Clear extra-files progress"
          phaseLabel={extraFilesProgress.phase || "clearing"}
          done={extraFilesProgress.done || 0}
          total={extraFilesProgress.total || 0}
          percent={extraFilesPercent}
          title={extraFilesProgress.current_title || ""}
          stats={[
            extraFilesProgress.shelved ? `shelved ${extraFilesProgress.shelved}` : "",
            extraFilesProgress.split ? `split ${extraFilesProgress.split}` : "",
            extraFilesProgress.applied ? `applied ${extraFilesProgress.applied}` : "",
            extraFilesProgress.failed ? `failed ${extraFilesProgress.failed}` : "",
          ]}
          statusLine={extraFilesStatusLine}
          meterLabel="Clear extra-files progress"
        />
      ) : null}
      {showPurgeProgress ? (
        <JobProgress
          className="ingest-progress review-extra-files-progress"
          testId="review-purge-duplicates-progress"
          kicker="Purge duplicates progress"
          phaseLabel={purgeProgress.phase || "purging"}
          done={purgeProgress.done || 0}
          total={purgeProgress.total || 0}
          percent={purgePercent}
          title={purgeProgress.current_title || ""}
          stats={[
            purgeProgress.purged ? `purged ${purgeProgress.purged}` : "",
            purgeProgress.shelf_twins ? `shelf ${purgeProgress.shelf_twins}` : "",
            purgeProgress.slip_twins ? `slip ${purgeProgress.slip_twins}` : "",
            purgeProgress.kept ? `kept ${purgeProgress.kept}` : "",
            purgeProgress.failed ? `failed ${purgeProgress.failed}` : "",
          ]}
          statusLine={purgeStatusLine}
          meterLabel="Purge duplicates progress"
        />
      ) : null}
      {showMigration ? (
        <JobProgress
          className="ingest-progress review-extra-files-progress"
          testId="review-bad-release-migration"
          kicker="Returning bad downloads to Wanted"
          phaseLabel={migration.status === "running" ? "returning" : migration.status}
          done={migration.done || 0}
          total={migration.total || 0}
          percent={
            Number(migration.total || 0) > 0
              ? Math.round((Number(migration.done || 0) / Number(migration.total)) * 100)
              : null
          }
          title={migration.current_title || ""}
          stats={[
            `returned ${Number(migration.returned || 0)}`,
            `left for you ${Number(migration.left_on_desk || 0)}`,
            migration.failed ? `failed ${migration.failed}` : "",
          ]}
          statusLine={badReleaseMigrationSummary(migration)}
          meterLabel="Returning bad downloads to Wanted"
        />
      ) : null}
      {groupNote ? (
        <p className="muted" role="status" data-testid="review-group-note">
          {groupNote}
        </p>
      ) : null}
      {loading ? (
        <section className="review-loading" data-testid="review-loading" aria-busy="true">
          <p className="muted">Warming the lamp on the Holds desk…</p>
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
      <div className="holds-desk-groups" data-testid="holds-desk-groups">
        {holdGroups.map((group) => (
          <section
            key={group.reason || "other"}
            className="holds-group ticket-enter"
            data-testid="holds-group"
            data-reason={group.reason || ""}
            aria-labelledby={`holds-group-${group.reason || "other"}`}
          >
            <header className="holds-group-head">
              <div>
                <h2 className="holds-group-title" id={`holds-group-${group.reason || "other"}`}>
                  {group.label}
                  <span className="holds-group-count muted"> · {group.works.length}</span>
                </h2>
                <p className="muted holds-group-hint">{group.hint}</p>
              </div>
              <div>
                <HoldsGroupActions group={group} onChanged={onGroupChanged} />
                <p className="chip holds-group-motion" data-testid="holds-group-motion">
                  Recommended: {recommendedMotionLabel(group.recommendedMotion)}
                </p>
              </div>
            </header>
            <ul className="stack holds-group-slips">
              {group.works.map((work) => (
                <HoldSlipCard
                  key={work.id}
                  work={work}
                  draft={drafts[work.id] || fieldsFromWork(work)}
                  focused={Boolean(focusId) && work.id === focusId}
                  focusRef={focusRef}
                  busyValue={busy[work.id]}
                  slipError={errors[work.id] || ""}
                  statusNote={ticketStatusNote(busy, actionNotes, work.id) || suggestNotes[work.id] || ""}
                  matchBag={matchBags[work.id]}
                  regrab={regrabs[work.id]}
                  onPatch={(key, value) => patch(work.id, key, value)}
                  onPrimary={() => runPrimary(work)}
                  onApply={() => apply(work)}
                  onSkip={() => skip(work)}
                  onRepair={() => repair(work)}
                  onRetry={() => retry(work)}
                  onRetrieve={(intent) => retrieveRelease(work, intent)}
                  onSuggest={() => suggestWithLlm(work)}
                  onApplyAuthority={(candidate) => applyAuthorityMatch(work, candidate)}
                  onRequestCandidate={(candidate) => requestRegrab(work, candidate)}
                  onUseListedMatch={(row) => applyListedMatch(work, row)}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
