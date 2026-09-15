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

export function reviewReasonCopy(reason) {
  if (reason === "no_payload") {
    return "No book, comic, or audio file at this path. Apply cannot invent a payload — point the folder at files this Librarian can read, set SAB complete root to map /downloads, or Skip.";
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
    return "A conversion is still needed (PDF book or CBR comic). Apply retries once files are readable.";
  }
  if (reason === "collision") {
    return "A file already exists at the library destination.";
  }
  return "Unexpected item in the bagging area. Confirm identity and the complete folder, then Apply or Skip.";
}
