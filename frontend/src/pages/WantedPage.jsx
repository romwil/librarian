import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import { WANTED_COPY, wantedDeskModel } from "../wantedDesk.js";
import { ThinkingButton } from "../components/Thinking.jsx";
import WarmLoad from "../components/WarmLoad.jsx";

const KINDS = ["audiobook", "book", "magazine", "comic", "music"];
const PAGE_SIZE = 50;

function downloaderMessage(error) {
  const message = humanError(error);
  if (/downloader did not answer|sabnzbd/i.test(`${message} ${error?.message || ""}`)) {
    return "The downloader did not answer.";
  }
  return "";
}

export default function WantedPage() {
  const { user } = useOutletContext() || {};
  const role = user?.role || "reader";
  const [items, setItems] = useState([]);
  const [kinds, setKinds] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [busyKind, setBusyKind] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ title: "", author: "", kind: "audiobook" });
  const [selected, setSelected] = useState({});
  const [inflight, setInflight] = useState({});
  const [attempts, setAttempts] = useState({});
  const [beyond, setBeyond] = useState({});
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkTarget, setBulkTarget] = useState("");
  const [status, setStatus] = useState("");
  const [sweep, setSweep] = useState({ enabled: false, open: 0, cap: 0, restorable: 0 });

  const viewingDismissed = status === "dismissed";

  function applyList(data) {
    setItems(data.items || []);
    setTotal(Number(data.total || 0));
    setKinds(Array.isArray(data.kinds) ? data.kinds : []);
    if (data.page) setPage(Number(data.page));
    if (data.sweep) setSweep(data.sweep);
  }

  function load(next = {}) {
    const pageNo = next.page ?? page;
    const kindKey = next.kind ?? kind;
    const statusKey = next.status ?? status;
    return api
      .wanted({ kind: kindKey, page: pageNo, pageSize: PAGE_SIZE, status: statusKey })
      .then((data) => {
        applyList(data);
        return data;
      })
      .catch((err) => setError(humanError(err)));
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .wanted({ kind, page, pageSize: PAGE_SIZE, status })
      .then((data) => {
        if (!alive) return;
        applyList(data);
      })
      .catch((err) => {
        if (alive) setError(humanError(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [kind, page, status]);

  const selectedCount = Object.keys(selected).length;
  const desk = wantedDeskModel({
    items,
    role,
    attempts,
    inflight,
    kind,
    selectedCount,
    total,
    includeDismissed: viewingDismissed,
    sweep,
  });
  const visibleIds = desk.rows.map((row) => row.id).filter(Boolean);
  const pageChecked = visibleIds.length > 0 && visibleIds.every((id) => selected[id]);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function chooseKind(nextKind) {
    setSelected({});
    setKind(nextKind);
    setPage(1);
  }

  function chooseStatus(nextStatus) {
    setSelected({});
    setStatus(nextStatus);
    setPage(1);
  }

  function togglePage() {
    const next = {};
    if (!pageChecked) {
      for (const id of visibleIds) next[id] = true;
    }
    setSelected(next);
  }

  function toggleRow(id) {
    setSelected((current) => {
      const next = { ...current };
      if (next[id]) delete next[id];
      else next[id] = true;
      return next;
    });
  }

  function noteResults(results) {
    setAttempts((current) => {
      const next = { ...current };
      for (const result of results || []) {
        if (!result?.id) continue;
        if (result.outcome === "downloader" || /sabnzbd/i.test(result.note || "")) {
          next[result.id] = { downloader: true, detail: "The downloader did not answer." };
        } else if (result.outcome === "hit") {
          next[result.id] = { outcome: "hit", detail: "A hit is on a slip." };
        } else if (result.outcome === "already_asked") {
          next[result.id] = { outcome: "already_asked", detail: "Already on a slip." };
        } else if (result.outcome === "miss") {
          next[result.id] = { outcome: "miss", detail: "Nothing found." };
        } else if (result.outcome === "rate_limited") {
          next[result.id] = { outcome: "rate_limited", detail: "The indexer asked us to wait." };
        } else if (result.outcome === "not_due") {
          delete next[result.id];
        }
      }
      return next;
    });
  }

  async function runSearch(body, ids, target) {
    if (bulkBusy) return;
    setBulkBusy(true);
    setBulkTarget(target || "");
    setError("");
    setInflight((current) => {
      const next = { ...current };
      for (const id of ids) next[id] = true;
      return next;
    });
    try {
      const data = await api.searchWanted(body);
      noteResults(data.results || []);
      await load();
    } catch (err) {
      const downloader = downloaderMessage(err);
      if (downloader) {
        setAttempts((current) => {
          const next = { ...current };
          for (const id of ids) next[id] = { downloader: true, detail: downloader };
          return next;
        });
      } else {
        setError(humanError(err));
      }
    } finally {
      setInflight((current) => {
        const next = { ...current };
        for (const id of ids) delete next[id];
        return next;
      });
      setBulkBusy(false);
      setBulkTarget("");
    }
  }

  function searchSelected() {
    const searchable = new Set(desk.rows.filter((row) => row.canSearchRow).map((row) => row.id));
    const ids = visibleIds.filter((id) => selected[id] && searchable.has(id));
    if (!ids.length) return;
    runSearch({ ids }, ids, "selected");
  }

  function searchAll() {
    runSearch(kind ? { all: true, kind } : { all: true }, visibleIds, "all");
  }

  async function findBeyond(row) {
    if (!row.id || inflight[row.id] || !row.canFindBeyond) return;
    setInflight((current) => ({ ...current, [row.id]: true }));
    setError("");
    try {
      const data = await api.wantedBeyond(row.id);
      setBeyond((current) => ({ ...current, [row.id]: data }));
      if (data?.beyond_error && /sabnzbd|downloader/i.test(String(data.beyond_error))) {
        setAttempts((current) => ({
          ...current,
          [row.id]: { downloader: true, detail: "The downloader did not answer." },
        }));
      } else if (!(data?.hits || []).length && !data?.beyond_error) {
        setAttempts((current) => ({
          ...current,
          [row.id]: { outcome: "miss", detail: "Nothing found." },
        }));
      }
    } catch (err) {
      const downloader = downloaderMessage(err);
      if (downloader) {
        setAttempts((current) => ({
          ...current,
          [row.id]: { downloader: true, detail: downloader },
        }));
      } else {
        setError(humanError(err));
      }
    } finally {
      setInflight((current) => {
        const next = { ...current };
        delete next[row.id];
        return next;
      });
    }
  }

  async function ask(row, hit) {
    if (!row.id || row.status === "asked" || busyId) return;
    setBusyId(row.id);
    setError("");
    try {
      const data = await api.askWanted(row.id, hit);
      noteResults([{ id: row.id, outcome: data.outcome, note: data.note }]);
      await load();
    } catch (err) {
      const downloader = downloaderMessage(err);
      if (downloader) {
        setAttempts((current) => ({
          ...current,
          [row.id]: { downloader: true, detail: downloader },
        }));
      } else {
        setError(humanError(err));
      }
    } finally {
      setBusyId("");
    }
  }

  async function confirmSlip(row) {
    if (!row.jobId || busyId) return;
    setBusyId(row.id);
    setError("");
    try {
      await api.confirmJob(row.jobId);
      await load();
    } catch (err) {
      const message = humanError(err);
      if (/nzbfinder|indexer token|not an asked slip|job not found/i.test(message)) {
        setError(message);
      } else {
        setAttempts((current) => ({
          ...current,
          [row.id]: { downloader: true, detail: "The downloader did not answer." },
        }));
      }
    } finally {
      setBusyId("");
    }
  }

  async function dismiss(id) {
    if (!id || busyId) return;
    setBusyId(id);
    setBusyKind("dismiss");
    setError("");
    try {
      await api.dismissWanted(id);
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusyId("");
      setBusyKind("");
    }
  }

  async function restore(id) {
    if (!id || busyId) return;
    setBusyId(id);
    setBusyKind("restore");
    setError("");
    try {
      await api.restoreWanted(id);
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusyId("");
      setBusyKind("");
    }
  }

  async function dismissSweep() {
    if (bulkBusy || desk.toolbar.dismissSweepDisabled) return;
    setBulkBusy(true);
    setBulkTarget("dismiss-sweep");
    setError("");
    try {
      await api.dismissSweepWanted();
      setSelected({});
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBulkBusy(false);
      setBulkTarget("");
    }
  }

  async function restoreSweep() {
    if (bulkBusy || desk.toolbar.restoreSweepDisabled) return;
    setBulkBusy(true);
    setBulkTarget("restore-sweep");
    setError("");
    try {
      await api.restoreSweepWanted();
      setSelected({});
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBulkBusy(false);
      setBulkTarget("");
    }
  }

  async function toggleSweep() {
    if (!desk.canToggleSweep || bulkBusy) return;
    setBulkBusy(true);
    setBulkTarget("sweep");
    setError("");
    try {
      const data = await api.setWantedSweep(!desk.sweepEnabled);
      if (data?.sweep) setSweep(data.sweep);
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBulkBusy(false);
      setBulkTarget("");
    }
  }

  async function add(event) {
    event.preventDefault();
    if (adding) return;
    const title = draft.title.trim();
    if (!title) {
      setError("A title is required.");
      return;
    }
    setAdding(true);
    setError("");
    try {
      await api.addWanted({
        title,
        author: draft.author.trim(),
        kind: draft.kind || "audiobook",
      });
      setDraft({ title: "", author: "", kind: draft.kind || "audiobook" });
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setAdding(false);
    }
  }

  const filterKinds = kinds.length ? kinds : KINDS.filter((name) => desk.rows.some((row) => row.kind === name));

  return (
    <div className="wanted-page page-settle" data-testid="wanted-page">
      <section className="browse-hero">
        <p className="kicker">Stacks</p>
        <h1>Wanted</h1>
        <p className="lede">Titles the house does not have yet.</p>
        <p className="lede" data-testid="wanted-fiction-only">
          {desk.sweepEnabled ? WANTED_COPY.sweepOn : WANTED_COPY.sweepOff}
        </p>
      </section>
      {error ? <p className="alert hall-alert">{error}</p> : null}
      {loading ? (
        <WarmLoad message="Opening Wanted…" testId="wanted-loading" />
      ) : (
        <>
          <div className="wanted-toolbar" data-testid="wanted-toolbar">
            <div className="chip-row" role="group" aria-label="Kind">
              <button
                type="button"
                className="chip"
                aria-pressed={kind === ""}
                onClick={() => chooseKind("")}
              >
                All
              </button>
              {filterKinds.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="chip"
                  aria-pressed={kind === name}
                  onClick={() => chooseKind(name)}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="chip-row" role="group" aria-label="Wanted status">
              <button
                type="button"
                className="chip"
                aria-pressed={!viewingDismissed}
                onClick={() => chooseStatus("")}
              >
                {WANTED_COPY.open}
              </button>
              <button
                type="button"
                className="chip"
                aria-pressed={viewingDismissed}
                onClick={() => chooseStatus("dismissed")}
              >
                {WANTED_COPY.recentlyDismissed}
              </button>
            </div>
            {desk.canSearch ? (
              <div className="cta-row compact">
                {viewingDismissed ? (
                  <ThinkingButton
                    type="button"
                    className="cta compact"
                    busy={bulkTarget === "restore-sweep"}
                    disabled={desk.toolbar.restoreSweepDisabled || bulkBusy}
                    onClick={restoreSweep}
                  >
                    {desk.toolbar.restoreSweepLabel}
                  </ThinkingButton>
                ) : (
                  <>
                    <ThinkingButton
                      type="button"
                      className="cta compact"
                      busy={bulkTarget === "selected"}
                      disabled={desk.toolbar.searchSelectedDisabled || bulkBusy}
                      onClick={searchSelected}
                      data-testid="wanted-search-selected"
                    >
                      {desk.toolbar.searchSelectedLabel}
                    </ThinkingButton>
                    <ThinkingButton
                      type="button"
                      className="cta outline compact"
                      busy={bulkTarget === "all"}
                      disabled={desk.toolbar.searchAllDisabled || bulkBusy}
                      onClick={searchAll}
                      data-testid="wanted-search-all"
                    >
                      {desk.toolbar.searchAllLabel}
                    </ThinkingButton>
                    <ThinkingButton
                      type="button"
                      className="cta outline compact"
                      busy={bulkTarget === "dismiss-sweep"}
                      disabled={desk.toolbar.dismissSweepDisabled || bulkBusy}
                      onClick={dismissSweep}
                    >
                      {desk.toolbar.dismissSweepLabel}
                    </ThinkingButton>
                  </>
                )}
                {desk.canToggleSweep ? (
                  <ThinkingButton
                    type="button"
                    className="cta outline compact"
                    busy={bulkTarget === "sweep"}
                    disabled={bulkBusy}
                    onClick={toggleSweep}
                  >
                    {desk.sweepEnabled ? WANTED_COPY.turnSweepOff : WANTED_COPY.turnSweepOn}
                  </ThinkingButton>
                ) : null}
              </div>
            ) : null}
          </div>
          {desk.empty ? (
            <p className="lede" data-testid="wanted-empty">
              {viewingDismissed
                ? "Nothing restorable right now."
                : kind
                  ? "Nothing of this kind is wanted right now."
                  : "Nothing is wanted right now."}
            </p>
          ) : (
            <ul className="wanted-list" data-testid="wanted-list">
              {desk.canSearch ? (
                <li className="wanted-select-page">
                  <label>
                    <input
                      type="checkbox"
                      checked={pageChecked}
                      onChange={togglePage}
                      aria-label={desk.toolbar.selectPageLabel}
                    />
                    {desk.toolbar.selectPageLabel}
                  </label>
                </li>
              ) : null}
              {desk.rows.map((row) => {
                const hits = beyond[row.id]?.hits || [];
                return (
                  <li key={row.id || row.title} className="wanted-row" data-testid="wanted-row">
                    <div className="wanted-copy">
                      {desk.canSearch && row.canSearchRow ? (
                        <label className="wanted-check">
                          <input
                            type="checkbox"
                            checked={Boolean(selected[row.id])}
                            onChange={() => toggleRow(row.id)}
                            aria-label={`Select ${row.title}`}
                          />
                        </label>
                      ) : null}
                      <div>
                        <p className="wanted-title">
                          {row.workId ? <Link to={`/works/${row.workId}`}>{row.title}</Link> : row.title}
                        </p>
                        <p className="muted">
                          {[row.author, row.kind, row.sourceLabel].filter(Boolean).join(" · ")}
                        </p>
                        <p className="muted" data-testid="wanted-status">
                          {row.statusLabel}
                          {row.statusDetail ? ` · ${row.statusDetail}` : ""}
                        </p>
                        {row.retryLine ? <p className="muted">{row.retryLine}</p> : null}
                      </div>
                    </div>
                    <div className="cta-row compact">
                      {row.bookShelf ? (
                        <Link className="cta compact" to={row.bookShelf.href} data-testid="wanted-book-shelf">
                          {row.bookShelf.label}
                        </Link>
                      ) : null}
                      {row.audioShelf ? (
                        <Link className="cta compact" to={row.audioShelf.href} data-testid="wanted-audio-shelf">
                          {row.audioShelf.label}
                        </Link>
                      ) : null}
                      {row.audioShelf ? (
                        <Link className="cta outline compact" to={row.audioShelf.listenHref} data-testid="wanted-listen">
                          Listen
                        </Link>
                      ) : null}
                      <ThinkingButton
                        type="button"
                        className="cta outline compact"
                        onClick={() => findBeyond(row)}
                        busy={Boolean(inflight[row.id]) && !bulkBusy}
                        disabled={Boolean(inflight[row.id]) || !row.canFindBeyond}
                        data-testid="wanted-find-beyond"
                      >
                        Find beyond
                      </ThinkingButton>
                      {row.status === "asked" && desk.canSearch && row.jobId ? (
                        <button
                          type="button"
                          className="cta compact"
                          onClick={() => confirmSlip(row)}
                          disabled={busyId === row.id}
                          data-testid="wanted-confirm"
                        >
                          Confirm
                        </button>
                      ) : null}
                      {row.canDismiss ? (
                        <ThinkingButton
                          type="button"
                          className="cta outline compact"
                          onClick={() => dismiss(row.id)}
                          busy={busyId === row.id && busyKind === "dismiss"}
                          disabled={busyId === row.id}
                          data-testid="wanted-dismiss"
                        >
                          Dismiss
                        </ThinkingButton>
                      ) : null}
                      {row.canRestore ? (
                        <ThinkingButton
                          type="button"
                          className="cta compact"
                          onClick={() => restore(row.id)}
                          busy={busyId === row.id && busyKind === "restore"}
                          disabled={busyId === row.id}
                        >
                          {WANTED_COPY.restore}
                        </ThinkingButton>
                      ) : null}
                    </div>
                    {beyond[row.id]?.beyond_error && !/sabnzbd|downloader/i.test(String(beyond[row.id].beyond_error)) ? (
                      <p className="muted" role="status">
                        {humanError(beyond[row.id].beyond_error)}
                      </p>
                    ) : null}
                    {hits.length ? (
                      <ul className="wanted-hits" data-testid="wanted-beyond-hits">
                        {hits.map((hit) => (
                          <li key={hit.guid || hit.title}>
                            <span>{hit.title || hit.book_title || "Release"}</span>
                            {desk.canSearch ? (
                              <button
                                type="button"
                                className="cta outline compact"
                                onClick={() => ask(row, hit)}
                                disabled={row.status === "asked" || busyId === row.id}
                              >
                                Ask
                              </button>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          {total > PAGE_SIZE ? (
            <div className="cta-row compact wanted-pager">
              <button
                type="button"
                className="cta outline compact"
                disabled={page <= 1}
                onClick={() => {
                  setSelected({});
                  setPage((current) => Math.max(1, current - 1));
                }}
              >
                Previous
              </button>
              <p className="muted">
                Page {page} of {pageCount}
              </p>
              <button
                type="button"
                className="cta outline compact"
                disabled={page >= pageCount}
                onClick={() => {
                  setSelected({});
                  setPage((current) => current + 1);
                }}
                data-testid="wanted-next-page"
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      )}
      {desk.canAdd ? (
        <form className="wanted-add" onSubmit={add} data-testid="wanted-add">
          <h2>Add to Wanted</h2>
          <label className="field">
            <span>Title</span>
            <input
              value={draft.title}
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              aria-label="Title"
            />
          </label>
          <label className="field">
            <span>Author</span>
            <input
              value={draft.author}
              onChange={(event) => setDraft((current) => ({ ...current, author: event.target.value }))}
              aria-label="Author"
            />
          </label>
          <label className="field">
            <span>Kind</span>
            <select
              value={draft.kind}
              onChange={(event) => setDraft((current) => ({ ...current, kind: event.target.value }))}
              aria-label="Kind"
            >
              {KINDS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="cta compact" disabled={adding} data-testid="wanted-add-submit">
            Add to Wanted
          </button>
        </form>
      ) : null}
    </div>
  );
}
