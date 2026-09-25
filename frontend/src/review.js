export function fieldsFromWork(work) {
  return {
    title: work.title || "",
    author: work.author || "",
    kind: work.kind || "book",
    isbn: work.isbn || "",
    asin: work.asin || "",
    series_name: work.series_name || "",
    series_index: work.series_index || "",
    year: work.year || "",
    folder: work.folder_path || work.storage_path || "",
  };
}

/** Dotted Usenet dumps / release tokens that should not stay as shelf titles. */
export function looksLikeDumpTitle(value) {
  const text = String(value || "").trim();
  if (!text) return true;
  const dots = (text.match(/\./g) || []).length;
  if (dots >= 3) return true;
  if (
    /\b(audio[\.\s_\-]*book|ebook|epub|mobi|azw3|hybrid|retail|proper|repack|bitbook|comic|cbr|cbz|mp3|flac|m4b|unabridged|abridged)\b/i.test(
      text,
    )
  ) {
    return true;
  }
  if (!text.includes(" - ") && text.length >= 48 && (text.match(/ /g) || []).length >= 6) {
    const words = text.split(/\s+/).filter(Boolean);
    const titled = words.filter((w) => /^[A-Z]/.test(w)).length;
    if (titled >= 6 && titled >= words.length * 0.6) return true;
  }
  return false;
}

export function applySuggestionToDraft(draft, suggestion) {
  if (!suggestion || typeof suggestion !== "object") return draft || {};
  const next = { ...(draft || {}) };
  for (const key of ["title", "author", "kind", "series_name", "series_index", "isbn", "year"]) {
    const value = suggestion[key];
    if (value == null || value === "") continue;
    next[key] = value;
  }
  return next;
}

export function applyBodyFromDraft(draft) {
  const body = {
    title: draft.title,
    author: draft.author,
    kind: draft.kind,
    isbn: draft.isbn,
    series_name: draft.series_name,
    series_index: draft.series_index,
    folder: draft.folder,
  };
  if (draft.year !== "" && draft.year != null) {
    const year = Number(draft.year);
    if (!Number.isNaN(year)) body.year = year;
  }
  return body;
}

/** Effective reason: live folder diagnosis can refine a stale no_payload. */
export function effectiveReviewReason(work) {
  const problem = work?.folder_diagnosis?.problem;
  const stored = String(work?.review_reason || "");
  if (problem === "unpack_stuck") return "unpack_stuck";
  if (problem === "missing_folder" && (stored === "no_payload" || !stored)) return "missing_folder";
  if (problem === "no_payload" && (!stored || stored === "no_payload")) return "no_payload";
  return stored || problem || "";
}

export function reviewReasonCopy(reason, diagnosis = {}) {
  if (reason === "quiet_hours") {
    return "Queued for tonight — quiet hours defer unpack and convert until the household window.";
  }
  if (reason === "unpack_stuck") {
    return "SABnzbd left archives in this folder. Try Repair (par2) when available, then Retry — or Apply to unpack rar/7z with unar.";
  }
  if (reason === "missing_folder") {
    return "That complete folder is missing on disk. Remap SAB’s path, paste a folder this process can read, or Skip.";
  }
  if (reason === "no_payload") {
    return "No book, comic, or audio file at this path. Apply cannot invent a payload — Request a new version beyond the shelves if the dump is empty.";
  }
  if (reason === "unknown_identity") {
    return "Identity is missing. Suggest with LLM when configured, or fill title and author by hand, then Apply.";
  }
  if (reason === "low_confidence") {
    return "Identify was unsure. Confirm the suggestion or correct the fields, then Apply.";
  }
  if (reason === "unexpected_kind") {
    return "Kind does not match a library shelf. Pick book, magazine, comic, audiobook, or music.";
  }
  if (reason === "extra_files") {
    const titles = Number(diagnosis?.distinct_title_count || 0);
    if (diagnosis?.collection_dump || titles >= 2) {
      const label = titles >= 2 ? `${titles} different titles` : "many different titles";
      return (
        `This folder looks like a multi-title collection dump (${label}), not leftover junk beside one book. ` +
        "Use Clear extra-files to shelve each title — you should not Apply one-by-one."
      );
    }
    return "Extra files in the complete folder. Confirm the identity and Apply to file what is there.";
  }
  if (reason === "convert_failed") {
    return "This comic still needs a clean CBZ. Apply retries CBR/PDF → CBZ remux for the shelf. Komga/Panels read CBZ only.";
  }
  if (reason === "comicvine_ambiguous") {
    return "Comic Vine found more than one plausible volume. Pick the right volume/issue below (or correct series + year), then Apply.";
  }
  if (reason === "comicvine_unmatched") {
    return "Comic Vine could not match this issue confidently. Confirm series, volume year, and issue — or Skip.";
  }
  if (reason === "audnexus_ambiguous") {
    return "Audnexus found more than one plausible audiobook. Pick the right ASIN match, then Apply — remux waits until this is resolved.";
  }
  if (reason === "audnexus_unmatched") {
    return "Audnexus could not match this audiobook confidently. Confirm title, author, or ASIN — pick a candidate, then Apply.";
  }
  if (reason === "collision") {
    return "Collision — a file already exists at the library destination (duplicate path or identity). Librarian will not silent-overwrite.";
  }
  return "Unexpected item in the bagging area. Confirm identity and the complete folder, then Apply or Skip.";
}

export function reviewSlipMeaning(reason, diagnosis = {}) {
  const titles = Number(diagnosis?.distinct_title_count || 0);
  if (reason === "extra_files" && (diagnosis?.collection_dump || titles >= 2)) {
    return (
      "Organize found many different books in one dump folder. That is normal for NYT / Usenet " +
      "collections — Clear extra-files peels them apart into one ticket per title."
    );
  }
  return "A slip means organize could not finish filing this download — it needs you before it can land on a shelf.";
}

export function reviewNextStepsCopy(reason, diagnosis = {}) {
  if (reason === "unpack_stuck") {
    return "Repair runs par2 when recovery volumes are present. Retry re-runs organize after unpack. Apply still tries unar — or Skip.";
  }
  if (reason === "missing_folder") {
    return "Check Settings → SAB complete root so /downloads maps to a path under /data this container can read. Paste the real folder, then Apply — or Skip.";
  }
  if (reason === "no_payload") {
    if (diagnosis?.suggested_folder) {
      return `Try the suggested folder below (readable files were nearby), then Apply — or Request a new version beyond the shelves.`;
    }
    return "Point Complete folder at a dump with readable media, Request a new version, or Skip.";
  }
  if (reason === "collision") {
    return collisionActionCopy();
  }
  if (reason === "extra_files") {
    const titles = Number(diagnosis?.distinct_title_count || 0);
    if (diagnosis?.collection_dump || titles >= 2) {
      return "Click Clear extra-files once — Librarian expands each title onto its own ingest ticket. Keep Apply for true one-book ambiguity only.";
    }
  }
  return "Confirm the fields and Complete folder, then Apply to file a ticket — or Skip to dismiss.";
}

/** Flags from GET /api/review → work.actions (backend review_slip_actions). */
export function reviewActionsFromWork(work = {}) {
  const actions = work?.actions || {};
  const reason = effectiveReviewReason(work);
  const findQuery = String(actions.find_query || "").trim();
  return {
    canRepair: Boolean(actions.can_repair),
    canRetry: Boolean(actions.can_retry),
    canRequestNew: Boolean(findQuery) || Boolean(work?.title),
    canRegrab: Boolean(actions.can_regrab),
    quietHours: Boolean(actions.quiet_hours) || reason === "quiet_hours",
    repairFailCount: Number(actions.repair_fail_count || work?.repair_fail_count || 0),
    findQuery: findQuery || [work?.title, work?.author].filter(Boolean).join(" "),
    findKind: String(work?.kind || "").trim(),
    reason,
    llmConfigured: Boolean(actions.llm_configured),
    canSuggestLlm: Boolean(actions.can_suggest_llm),
    needsLlmSuggest: Boolean(actions.needs_llm_suggest) || looksLikeDumpTitle(work?.title),
  };
}

/** Deep-link for Request a new version — Confirm still required on Find. */
export function reviewFindHref(work = {}) {
  const actions = reviewActionsFromWork(work);
  const q = actions.findQuery;
  const kind = actions.findKind && actions.findKind !== "gap" ? actions.findKind : "";
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  const qs = params.toString();
  return qs ? `/find?${qs}` : "/find";
}

export function unpackStuckWorks(works = []) {
  return (works || []).filter((work) => effectiveReviewReason(work) === "unpack_stuck");
}

export function extraFilesWorks(works = []) {
  return (works || []).filter((work) => effectiveReviewReason(work) === "extra_files");
}

/** Structured diagnosis block for a Review slip. */
export function reviewDiagnosisCopy(work) {
  const reason = effectiveReviewReason(work);
  const diagnosis = work?.folder_diagnosis || {};
  const whatsWrong =
    reason === "unpack_stuck"
      ? `Archives remain (${diagnosis.archive_count || "some"} rar/7z) and no readable media.`
      : reason === "missing_folder"
        ? "The complete folder path does not exist where Librarian can read it."
        : reason === "no_payload"
          ? diagnosis.junk_count
            ? `Only non-media files (${diagnosis.junk_count}) — no book, comic, or audio.`
            : "No readable book, comic, or audio file here."
          : reviewReasonCopy(reason, diagnosis);
  return {
    meaning: reviewSlipMeaning(reason, diagnosis),
    tried: diagnosis.tried || "Checked the complete folder for files this Librarian can shelve.",
    lookedFor: diagnosis.looked_for || "book, comic, or audio files",
    whatsWrong,
    nextSteps: reviewNextStepsCopy(reason, diagnosis),
    pathNote: diagnosis.path_note || "",
    suggestedFolder: diagnosis.suggested_folder || "",
  };
}

/** Extra guidance under collision slips (Skip vs Apply). */
export function collisionActionCopy() {
  return "Skip keeps what’s already on the shelf and dismisses this slip. Apply will not overwrite — change title, author, series, or folder so the destination is free, then Apply.";
}

const COLLISION_DRAFT_KEYS = ["title", "author", "kind", "isbn", "series_name", "series_index", "folder"];

/** True when collision draft still matches the parked work (Apply would 400). */
export function collisionDraftUnchanged(draft, work) {
  const base = fieldsFromWork(work || {});
  const next = draft || base;
  return COLLISION_DRAFT_KEYS.every((key) => String(next[key] ?? "") === String(base[key] ?? ""));
}

/** Apply is allowed once identity/folder changes enough to seek a free destination. */
export function collisionApplyAllowed(reason, draft, work) {
  if (reason !== "collision") return true;
  return !collisionDraftUnchanged(draft, work);
}

/** One-line Queue copy for job status `review` → household **Needs you**. */
export function queueReviewReasonCopy(reason) {
  if (reason === "unpack_stuck") {
    return "Archives left unpacked — open Review.";
  }
  if (reason === "missing_folder") {
    return "Complete folder missing — open Review.";
  }
  if (reason === "no_payload") {
    return "No readable book, comic, or audio file — open Review.";
  }
  if (reason === "unknown_identity") {
    return "Identity unclear — open Review to name it.";
  }
  if (reason === "low_confidence") {
    return "Identify was unsure — confirm it in Review.";
  }
  if (reason === "unexpected_kind") {
    return "Wrong shelf kind — pick one in Review.";
  }
  if (reason === "extra_files") {
    return "Multi-title dump or extra files — open Review (Clear extra-files for collections).";
  }
  if (reason === "convert_failed") {
    return "Conversion still needed — open Review.";
  }
  if (reason === "collision") {
    return "Already on the shelf at that path — Open Review.";
  }
  return "Waiting in Review — the house isn’t sure how to shelve this.";
}

export function extraFilesReprocessIsRunning(status) {
  return String(status?.status || "") === "running";
}

/** True while a clear job is running or the last run result is still on screen. */
export function extraFilesReprocessIsActive(status) {
  const state = String(status?.status || "");
  return state === "running" || state === "completed" || state === "failed";
}

/** Show the Clear extra-files progress meter (including mid-run after refresh). */
export function reviewExtraFilesProgressVisible(progress, clearing = false) {
  if (clearing || extraFilesReprocessIsRunning(progress)) return true;
  return extraFilesReprocessIsActive(progress);
}

/**
 * Keep Clear extra-files visible for visible slips, server backlog, or an active/recent job —
 * not only when the current Review page slice still has extra_files rows.
 */
export function reviewBulkClearVisible({
  visibleCount = 0,
  backlogCount = 0,
  clearing = false,
  progress = null,
} = {}) {
  if (Number(visibleCount) > 0) return true;
  if (Number(backlogCount) > 0) return true;
  if (clearing || extraFilesReprocessIsRunning(progress)) return true;
  if (extraFilesReprocessIsActive(progress)) return true;
  return false;
}

/** Bulk CTA row: unpack Repair/Retry and/or Clear/Purge, or mid-job progress alone. */
export function reviewBulkRowVisible({
  unpackCount = 0,
  showClear = false,
  showPurge = false,
  showProgress = false,
} = {}) {
  return Boolean(Number(unpackCount) > 0 || showClear || showPurge || showProgress);
}

/** 0–100 for the Clear extra-files meter; null when total is unknown. */
export function extraFilesReprocessProgressPercent(status) {
  if (!status || typeof status !== "object") return null;
  const total = Number(status.total || 0);
  if (total <= 0) return null;
  const done = Number(status.done || 0);
  if (!Number.isFinite(done)) return null;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

/** Household progress line for Clear extra-files polling. */
export function extraFilesReprocessProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Clear extra-files failed.";
  const done = Number(status.done || 0);
  const total = Number(status.total || 0);
  const shelved = Number(status.shelved || 0);
  const split = Number(status.split || 0);
  const applied = Number(status.applied || 0);
  const failed = Number(status.failed || 0);
  const title = String(status.current_title || "").trim();
  const pct = extraFilesReprocessProgressPercent(status);
  if (state === "completed") {
    const result = status.result || {};
    const s = Number(result.shelved != null ? result.shelved : shelved);
    const sp = Number(result.split != null ? result.split : split);
    const a = Number(result.applied != null ? result.applied : applied);
    const f = Number(result.failed != null ? result.failed : failed);
    const parts = [];
    if (s) parts.push(`shelved ${s}`);
    if (sp) parts.push(`split ${sp}`);
    if (a) parts.push(`applied ${a}`);
    if (f) parts.push(`failed ${f}`);
    if (!parts.length) return "Finished clearing extra-files slips.";
    return `Extra files: ${parts.join(", ")}.`;
  }
  const count = total > 0 ? `${done} of ${total}` : done ? `${done} done` : "";
  const pctBit = pct != null ? `${pct}%` : "";
  const head = ["Clearing extra-files", count, pctBit].filter(Boolean).join(" · ");
  const tallies = [];
  if (shelved) tallies.push(`shelved ${shelved}`);
  if (split) tallies.push(`split ${split}`);
  if (applied) tallies.push(`applied ${applied}`);
  if (failed) tallies.push(`failed ${failed}`);
  const mid = tallies.length ? ` · ${tallies.join(" · ")}` : "";
  const tail = title ? ` · ${title}` : "";
  return `${head}${mid}${tail}` || "Clearing extra-files…";
}

export function purgeDuplicatesIsRunning(status) {
  return String(status?.status || "") === "running";
}

export function purgeDuplicatesIsActive(status) {
  const state = String(status?.status || "");
  return state === "running" || state === "completed" || state === "failed";
}

export function reviewPurgeProgressVisible(progress, purging = false) {
  if (purging || purgeDuplicatesIsRunning(progress)) return true;
  return purgeDuplicatesIsActive(progress);
}

/** Keep Purge duplicates visible for any Review backlog or an active/recent job. */
export function reviewBulkPurgeVisible({
  visibleCount = 0,
  backlogCount = 0,
  purging = false,
  progress = null,
} = {}) {
  if (Number(visibleCount) > 0) return true;
  if (Number(backlogCount) > 0) return true;
  if (purging || purgeDuplicatesIsRunning(progress)) return true;
  if (purgeDuplicatesIsActive(progress)) return true;
  return false;
}

export function purgeDuplicatesProgressPercent(status) {
  if (!status || typeof status !== "object") return null;
  const total = Number(status.total || 0);
  if (total <= 0) return null;
  const done = Number(status.done || 0);
  if (!Number.isFinite(done)) return null;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

export function purgeDuplicatesProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Purge duplicates failed.";
  const done = Number(status.done || 0);
  const total = Number(status.total || 0);
  const purged = Number(status.purged || 0);
  const shelf = Number(status.shelf_twins || 0);
  const slip = Number(status.slip_twins || 0);
  const kept = Number(status.kept || 0);
  const failed = Number(status.failed || 0);
  const title = String(status.current_title || "").trim();
  const pct = purgeDuplicatesProgressPercent(status);
  if (state === "completed") {
    const result = status.result || {};
    const p = Number(result.purged != null ? result.purged : purged);
    const sh = Number(result.shelf_twins != null ? result.shelf_twins : shelf);
    const sl = Number(result.slip_twins != null ? result.slip_twins : slip);
    const k = Number(result.kept != null ? result.kept : kept);
    const f = Number(result.failed != null ? result.failed : failed);
    const parts = [];
    if (p) parts.push(`purged ${p}`);
    if (sh) parts.push(`shelf twins ${sh}`);
    if (sl) parts.push(`slip twins ${sl}`);
    if (k) parts.push(`kept ${k}`);
    if (f) parts.push(`failed ${f}`);
    if (!parts.length) return "Finished purging duplicates — nothing safely redundant.";
    return `Duplicates: ${parts.join(", ")}.`;
  }
  const count = total > 0 ? `${done} of ${total}` : done ? `${done} done` : "";
  const pctBit = pct != null ? `${pct}%` : "";
  const phase = String(status.phase || "purging").trim() || "purging";
  const head = [`Purging duplicates (${phase})`, count, pctBit].filter(Boolean).join(" · ");
  const tallies = [];
  if (purged) tallies.push(`purged ${purged}`);
  if (shelf) tallies.push(`shelf ${shelf}`);
  if (slip) tallies.push(`slip ${slip}`);
  if (kept) tallies.push(`kept ${kept}`);
  if (failed) tallies.push(`failed ${failed}`);
  const mid = tallies.length ? ` · ${tallies.join(" · ")}` : "";
  const tail = title ? ` · ${title}` : "";
  return `${head}${mid}${tail}` || "Purging duplicates…";
}
