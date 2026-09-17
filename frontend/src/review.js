export function fieldsFromWork(work) {
  return {
    title: work.title || "",
    author: work.author || "",
    kind: work.kind || "book",
    isbn: work.isbn || "",
    series_name: work.series_name || "",
    series_index: work.series_index || "",
    year: work.year || "",
    folder: work.folder_path || work.storage_path || "",
  };
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

export function reviewReasonCopy(reason) {
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
    return "Identity is missing. Fill title, author, ISBN or series/issue, then Apply.";
  }
  if (reason === "low_confidence") {
    return "Identify was unsure. Confirm or correct the fields, then Apply.";
  }
  if (reason === "unexpected_kind") {
    return "Kind does not match a library shelf. Pick book, magazine, comic, audiobook, or music.";
  }
  if (reason === "extra_files") {
    return "Extra files in the complete folder. Confirm the identity and Apply to file what is there.";
  }
  if (reason === "convert_failed") {
    return "This comic is still only CBR (RAR). Apply retries converting it to CBZ for the Reading Room. PDF comics open as PDF — no conversion needed.";
  }
  if (reason === "collision") {
    return "Collision — a file already exists at the library destination (duplicate path or identity). Librarian will not silent-overwrite.";
  }
  return "Unexpected item in the bagging area. Confirm identity and the complete folder, then Apply or Skip.";
}

export function reviewSlipMeaning() {
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
          : reviewReasonCopy(reason);
  return {
    meaning: reviewSlipMeaning(),
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
    return "Extra files in the dump — confirm in Review.";
  }
  if (reason === "convert_failed") {
    return "Conversion still needed — open Review.";
  }
  if (reason === "collision") {
    return "Already on the shelf at that path — Open Review.";
  }
  return "Waiting in Review — the house isn’t sure how to shelve this.";
}
