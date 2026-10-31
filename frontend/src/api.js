import { browseQueryParams } from "./browse.js";
import { detailText } from "./copy.js";

const API = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text.trim() };
    }
  }
  if (!response.ok) {
    const error = new Error(detailText(data.detail) || response.statusText);
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

export const api = {
  health: () => request("/health"),
  status: () => request("/status"),
  features: () => request("/features"),
  me: () => request("/auth/me"),
  login: (username, password) =>
    request("/auth/local/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  validateInvite: (token) => request(`/invites/validate?token=${encodeURIComponent(token)}`),
  redeem: (token, username, password) =>
    request("/invites/redeem/local", { method: "POST", body: JSON.stringify({ token, username, password }) }),
  mintInvite: (role) => request("/invites", { method: "POST", body: JSON.stringify({ role }) }),
  hall: () => request("/hall"),
  libraryCard: () => request("/library-card"),
  gapsLocal: () => request("/gaps/local"),
  browse: (filters = {}) => {
    const { offset, limit, ...rest } = filters;
    const qs = browseQueryParams(rest, { offset, limit }).toString();
    return request(`/browse${qs ? `?${qs}` : ""}`);
  },
  browseFacets: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.kind) params.set("kind", String(filters.kind));
    if (filters.shelf) params.set("shelf", String(filters.shelf));
    const qs = params.toString();
    return request(`/browse/facets${qs ? `?${qs}` : ""}`);
  },
  search: (q, extras = {}) => {
    const { beyond = false, kind = "", mode = "", title, author, isbn, series, issue, artist, album, year } = extras;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (beyond) params.set("beyond", "1");
    if (kind) params.set("kind", kind);
    if (mode) params.set("mode", mode);
    const fields = { title, author, isbn, series, issue, artist, album, year };
    for (const [key, value] of Object.entries(fields)) {
      if (value) params.set(key, value);
    }
    return request(`/search?${params.toString()}`);
  },
  suggest: ({ field, kind = "", q = "", limit = 12, signal } = {}) => {
    const params = new URLSearchParams();
    if (field) params.set("field", field);
    if (kind) params.set("kind", kind);
    if (q) params.set("q", q);
    if (limit) params.set("limit", String(limit));
    return request(`/suggest?${params.toString()}`, signal ? { signal } : {});
  },
  refreshSuggestCache: (external = false) =>
    request(`/settings/suggest-cache${external ? "?external=1" : ""}`, { method: "POST" }),
  work: (id) => request(`/works/${id}`),
  favorite: (id) => request(`/works/${id}/favorite`, { method: "POST" }),
  shelves: () => request("/shelves"),
  createShelf: (name, { shared = true } = {}) =>
    request("/shelves", { method: "POST", body: JSON.stringify({ name, shared: Boolean(shared) }) }),
  shareShelf: (id, shared = true) =>
    request(`/shelves/${encodeURIComponent(id)}/share`, {
      method: "POST",
      body: JSON.stringify({ shared: Boolean(shared) }),
    }),
  deleteShelf: (id) => request(`/shelves/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addToShelf: (shelfId, workId) =>
    request(`/shelves/${encodeURIComponent(shelfId)}/works/${encodeURIComponent(workId)}`, { method: "POST" }),
  removeFromShelf: (shelfId, workId) =>
    request(`/shelves/${encodeURIComponent(shelfId)}/works/${encodeURIComponent(workId)}`, { method: "DELETE" }),
  requestItem: (item) => request("/request", { method: "POST", body: JSON.stringify(item) }),
  addMissing: (items) =>
    request("/lists/add-missing", { method: "POST", body: JSON.stringify({ items: items || [] }) }),
  shelvePublicDomain: (edition) =>
    request("/public-domain/shelve", { method: "POST", body: JSON.stringify(edition || {}) }),
  wanted: ({ kind = "", page = 1, pageSize = 50, status = "" } = {}) => {
    const params = new URLSearchParams();
    if (kind) params.set("kind", kind);
    if (status) params.set("status", status);
    if (page) params.set("page", String(page));
    if (pageSize) params.set("page_size", String(pageSize));
    const qs = params.toString();
    return request(`/wanted${qs ? `?${qs}` : ""}`);
  },
  addWanted: (body) => request("/wanted", { method: "POST", body: JSON.stringify(body || {}) }),
  dismissWanted: (id) => request(`/wanted/${encodeURIComponent(id)}/dismiss`, { method: "POST" }),
  searchWanted: (body) => request("/wanted/search", { method: "POST", body: JSON.stringify(body || {}) }),
  wantedBeyond: (id) => request(`/wanted/${encodeURIComponent(id)}/beyond`, { method: "POST" }),
  askWanted: (id, hit) =>
    request(`/wanted/${encodeURIComponent(id)}/ask`, { method: "POST", body: JSON.stringify(hit || {}) }),
  review: (work = "") =>
    request(`/review${work ? `?work=${encodeURIComponent(work)}` : ""}`),
  reviewAcceptClear: (reason) =>
    request("/review/accept-clear", { method: "POST", body: JSON.stringify({ reason: reason || "" }) }),
  reviewApply: (id, body) => request(`/review/${id}/apply`, { method: "POST", body: JSON.stringify(body) }),
  reviewSkip: (id) => request(`/review/${id}/skip`, { method: "POST" }),
  reviewRepair: (id) => request(`/review/${id}/repair`, { method: "POST" }),
  reviewRetry: (id) => request(`/review/${id}/retry`, { method: "POST" }),
  reviewSuggest: (id) => request(`/review/${id}/suggest`, { method: "POST" }),
  reviewReprocessExtraFiles: (limit = 0) =>
    request(`/review/reprocess-extra-files${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`, {
      method: "POST",
    }),
  reviewReprocessExtraFilesStatus: () => request("/review/reprocess-extra-files/status"),
  reviewPurgeDuplicates: (limit = 0) =>
    request(`/review/purge-duplicates${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`, {
      method: "POST",
    }),
  reviewPurgeDuplicatesStatus: () => request("/review/purge-duplicates/status"),
  reviewBulkByReason: ({ reason = "", action = "", workIds = [], dryRun = false } = {}) =>
    request("/review/bulk-by-reason", {
      method: "POST",
      body: JSON.stringify({ reason, action, work_ids: workIds, dry_run: Boolean(dryRun) }),
    }),
  reviewSuggestBatch: (limit = 0) =>
    request(`/review/suggest-batch${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`, {
      method: "POST",
    }),
  reviewSuggestBatchStatus: () => request("/review/suggest-batch/status"),
  reviewApplyTrusted: () => request("/review/apply-trusted", { method: "POST" }),
  reviewBadReleaseMigrationStatus: () => request("/review/bad-release-migration/status"),
  maintainPurgeShells: (limit = 0) =>
    request(`/maintain/purge-shells${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`, {
      method: "POST",
    }),
  maintainPurgeShellsPreview: (limit = 0) =>
    request(`/maintain/purge-shells/preview${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`),
  maintainPurgeShellsStatus: () => request("/maintain/purge-shells/status"),
  maintainSplitMixedKinds: (limit = 0) =>
    request(`/maintain/split-mixed-kinds${limit ? `?limit=${encodeURIComponent(String(limit))}` : ""}`, {
      method: "POST",
    }),
  maintainSplitMixedKindsStatus: () => request("/maintain/split-mixed-kinds/status"),
  maintainCleanup: (approve = false) =>
    request(`/maintain/cleanup${approve ? "?approve=1" : ""}`, { method: "POST" }),
  maintainCleanupStatus: () => request("/maintain/cleanup/status"),
  maintainCleanupRestore: () => request("/maintain/cleanup/restore", { method: "POST" }),
  maintainCleanupEmpty: () => request("/maintain/cleanup/empty", { method: "POST" }),
  maintainShelfHealth: () => request("/maintain/shelf-health"),
  maintainMorningBrief: () => request("/maintain/morning-brief"),
  maintainJobsStatus: () => request("/maintain/jobs/status"),
  maintainIndexerScorecard: () => request("/maintain/indexer-scorecard"),
  maintainIndexerMute: (hostId) =>
    request(`/maintain/indexer-scorecard/${encodeURIComponent(hostId)}/mute`, { method: "POST" }),
  maintainIndexerUnmute: (hostId) =>
    request(`/maintain/indexer-scorecard/${encodeURIComponent(hostId)}/unmute`, { method: "POST" }),
  maintainGroomingUndo: () => request("/maintain/grooming-undo"),
  maintainGroomingUndoRestore: () => request("/maintain/grooming-undo", { method: "POST" }),
  maintainCalibreRenormalize: () => request("/maintain/calibre-renormalize"),
  maintainCalibreRenormalizeApply: () => request("/maintain/calibre-renormalize", { method: "POST" }),
  queue: () => request("/queue"),
  queueTick: () => request("/queue/tick", { method: "POST" }),
  confirmJob: (id) => request(`/queue/${id}/confirm`, { method: "POST" }),
  gaps: () => request("/gaps"),
  confirmGap: (item) => request("/gaps/confirm", { method: "POST", body: JSON.stringify(item) }),
  settings: () => request("/settings"),
  saveSettings: (body) => request("/settings", { method: "PUT", body: JSON.stringify(body) }),
  testMail: (body = {}) => request("/settings/mail/test", { method: "POST", body: JSON.stringify(body) }),
  people: () => request("/people"),
  promote: (id) => request(`/music/${id}/promote`, { method: "POST" }),
  pingIndexer: () => request("/indexers/ping", { method: "POST" }),
  absMatch: () => request("/settings/abs-match", { method: "POST" }),
  rssFeeds: () => request("/rss"),
  saveRss: (body) => request("/rss", { method: "POST", body: JSON.stringify(body) }),
  updateRss: (id, body) => request(`/rss/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteRss: (id) => request(`/rss/${id}`, { method: "DELETE" }),
  pollRss: () => request("/rss/poll", { method: "POST" }),
  noted: () => request("/noted", { signal: AbortSignal.timeout(20000) }),
  refreshNoted: () => request("/maintain/noted/refresh", { method: "POST" }),
  notedHistory: ({ listName, start, end }) =>
    request(`/noted/history?list_name=${encodeURIComponent(listName)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  addMissingNotedHistory: (items) =>
    request("/noted/history/add-missing", { method: "POST", body: JSON.stringify({ items: items || [] }) }),
  discover: (extras = {}) => {
    const params = new URLSearchParams();
    if (extras.kind) params.set("kind", extras.kind);
    if (extras.cat) params.set("cat", extras.cat);
    if (extras.limit) params.set("limit", String(extras.limit));
    if (extras.offset) params.set("offset", String(extras.offset));
    if (extras.page) params.set("page", String(extras.page));
    const qs = params.toString();
    return request(`/discover${qs ? `?${qs}` : ""}`);
  },
  listPresets: () => request("/lists/presets"),
  llmList: ({ preset = "hardcover-fiction", date = "current", query = "" } = {}) =>
    request("/lists/llm", {
      method: "POST",
      body: JSON.stringify({ preset, date, query: query || "" }),
    }),
  llmListChase: (items = []) =>
    request("/lists/llm/chase", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  scanShelves: () => request("/settings/scan", { method: "POST" }),
  scanStatus: () => request("/settings/scan/status"),
  enrichShelves: () => request("/settings/enrich", { method: "POST" }),
  enrichStatus: () => request("/settings/enrich/status"),
  enrichWork: (id) => request(`/works/${id}/enrich`, { method: "POST" }),
  updateWorkMetadata: (id, body) =>
    request(`/works/${id}/metadata`, { method: "PATCH", body: JSON.stringify(body) }),
  matchCandidates: (id) => request(`/works/${id}/match-candidates`),
  applyMatch: (id, matchKey) =>
    request(`/works/${id}/apply-match`, { method: "POST", body: JSON.stringify({ match_key: matchKey }) }),
  clearEnrich: (id) => request(`/works/${id}/clear-enrich`, { method: "POST" }),
  importGoodreads: (file) => {
    const body = new FormData();
    body.append("file", file);
    return fetch(`${API}/settings/goodreads`, {
      method: "POST",
      credentials: "include",
      body,
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(detailText(data.detail) || response.statusText);
        error.status = response.status;
        error.payload = data;
        throw error;
      }
      return data;
    });
  },
  indexers: () => request("/indexers"),
  progress: (id, body = {}) => request(`/works/${id}/progress`, { method: "POST", body: JSON.stringify(body) }),
  chapters: (id, fileId = "") => {
    const params = new URLSearchParams();
    if (fileId) params.set("file", String(fileId));
    const qs = params.toString();
    return request(`/works/${id}/chapters${qs ? `?${qs}` : ""}`);
  },
  convert: (id, format) => request(`/works/${id}/convert`, { method: "POST", body: JSON.stringify({ format }) }),
  fs: (path = "") => request(`/fs?path=${encodeURIComponent(path || "")}`),
  ingest: (path) => request("/ingest", { method: "POST", body: JSON.stringify({ path }) }),
  ingestPreview: (path) =>
    request("/ingest/preview", { method: "POST", body: JSON.stringify({ path }) }),
  ingestStatus: () => request("/ingest/status"),
  prefs: () => request("/prefs"),
  savePrefs: (body) => request("/prefs", { method: "PUT", body: JSON.stringify(body) }),
  notifications: (params) => {
    const qs = params instanceof URLSearchParams ? params.toString() : "";
    return request(`/notifications${qs ? `?${qs}` : ""}`);
  },
  markNotificationsSeen: (body) =>
    request("/notifications/seen", { method: "POST", body: JSON.stringify(body || {}) }),
  notificationPrefs: () => request("/notifications/prefs"),
  saveNotificationPrefs: (body) =>
    request("/notifications/prefs", { method: "PUT", body: JSON.stringify(body || {}) }),
  testNotification: (body) =>
    request("/notifications/test", { method: "POST", body: JSON.stringify(body || {}) }),
  pushNewsletter: (body) =>
    request("/newsletters/push", { method: "POST", body: JSON.stringify(body || { scope: "self", force: true }) }),
  runNewsletters: () => request("/newsletters/run", { method: "POST", body: "{}" }),
  whispers: (id) => request(`/works/${id}/whispers`),
  addWhisper: (id, body) => request(`/works/${id}/whispers`, { method: "POST", body: JSON.stringify({ body }) }),
  finishEta: ({ missingCount, kind = "", totalBytes = null, multipart = false } = {}) =>
    request("/find/finish-eta", {
      method: "POST",
      body: JSON.stringify({
        missing_count: missingCount,
        kind: kind || "",
        total_bytes: totalBytes != null ? totalBytes : undefined,
        multipart: Boolean(multipart),
      }),
    }),
  reviewRegrab: (id) => request(`/review/${id}/regrab`),
  reviewRetrieve: (id, intent) =>
    request(`/review/${id}/retrieve`, {
      method: "POST",
      body: JSON.stringify({ intent }),
    }),
  quietHours: () => request("/settings/quiet-hours"),
  saveQuietHours: (body) => request("/settings/quiet-hours", { method: "PUT", body: JSON.stringify(body) }),
};
