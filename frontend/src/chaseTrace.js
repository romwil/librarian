/** Bestsellers chase diagnostic trail helpers (collapsed disclosure). */

function trimmed(value) {
  return String(value || "").trim();
}

export function chaseTraceSummary(chase = {}) {
  const trace = chase?.trace && typeof chase.trace === "object" ? chase.trace : null;
  if (!trace) return "";
  const book = trace.book || {};
  const audio = trace.audiobook || {};
  const bits = [];
  const bookRaw = Number(book.raw_count) || 0;
  const audioRaw = Number(audio.raw_count) || 0;
  bits.push(`ebook raw ${bookRaw}`);
  bits.push(`audiobook raw ${audioRaw}`);
  if (book.error) bits.push(`ebook: ${trimmed(book.error)}`);
  if (audio.error) bits.push(`audiobook: ${trimmed(audio.error)}`);
  if (!chase.book_hit?.guid && bookRaw > 0) bits.push("ebook hits filtered or missing guid");
  if (!chase.audiobook_hit?.guid && audioRaw > 0) bits.push("audiobook hits filtered or missing guid");
  return bits.filter(Boolean).join(" · ");
}

export function chaseConversationLines(chase = {}) {
  const rows = chase?.trace?.conversation;
  if (!Array.isArray(rows)) return [];
  return rows
    .map((row) => {
      const role = trimmed(row?.role) || "note";
      const content = trimmed(row?.content);
      return content ? { role, content } : null;
    })
    .filter(Boolean);
}

export function chaseResultRows(chase = {}) {
  const out = [];
  for (const lane of ["book", "audiobook"]) {
    const results = chase?.trace?.[lane]?.results;
    if (!Array.isArray(results)) continue;
    for (const row of results) {
      out.push({
        lane,
        decision: trimmed(row?.decision) || "unknown",
        reason: trimmed(row?.reason),
        title: trimmed(row?.title) || trimmed(row?.book_title) || "(untitled)",
        guid: trimmed(row?.guid),
        kind: trimmed(row?.kind),
        author: trimmed(row?.author),
        host: trimmed(row?.host_name),
        size: row?.size,
        notes: Array.isArray(row?.notes) ? row.notes.map(trimmed).filter(Boolean) : [],
      });
    }
  }
  return out;
}

export function chaseStepLines(chase = {}) {
  const out = [];
  for (const lane of ["book", "audiobook"]) {
    const steps = chase?.trace?.[lane]?.steps;
    if (!Array.isArray(steps)) continue;
    for (const step of steps) {
      const detail = trimmed(step?.detail);
      if (!detail) continue;
      out.push({ lane, step: trimmed(step?.step) || "step", detail });
    }
  }
  return out;
}

export function chaseCandidateRows(chase = {}) {
  const out = [];
  for (const lane of ["book", "audiobook"]) {
    const fromTrace = chase?.trace?.[lane]?.candidates;
    const fromTop = chase?.[`${lane}_candidates`];
    const rows = Array.isArray(fromTrace) && fromTrace.length ? fromTrace : fromTop;
    if (!Array.isArray(rows)) continue;
    for (const row of rows) {
      const guid = trimmed(row?.guid);
      if (!guid) continue;
      out.push({
        lane,
        guid,
        title: trimmed(row?.title) || trimmed(row?.book_title) || "(untitled)",
        rank: row?.rank || null,
        note: trimmed(row?.note),
        method: trimmed(chase?.trace?.[lane]?.rank_method),
      });
    }
  }
  return out;
}
