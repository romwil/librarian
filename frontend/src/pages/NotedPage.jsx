import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import NotedBookCard from "../components/NotedBookCard.jsx";
import WarmLoad from "../components/WarmLoad.jsx";
import { humanError } from "../copy.js";
import {
  collapseNotedBooks,
  listFormatActions,
  notedBookStatus,
  notedFindHref,
  notedSearchHref,
  notedWantedBody,
  weekCountLabel,
} from "../noted.js";

function itemKey(item, kind) {
  return `${item?.title || ""}|${item?.author || ""}|${item?.isbn || ""}|${kind}`;
}

export default function NotedPage() {
  const [searchParams] = useSearchParams();
  const [payload, setPayload] = useState(null);
  const [activeList, setActiveList] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState({});
  const [busy, setBusy] = useState("");
  const selectedList =
    searchParams.get("preset") === "nyt" && searchParams.get("list")
      ? `nyt-${searchParams.get("list")}`
      : "";

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .noted()
      .then((data) => {
        if (!alive) return;
        setPayload(data);
        setActiveList((current) =>
          data?.lists?.some((list) => list.id === selectedList)
            ? selectedList
            : current || data?.lists?.[0]?.id || "",
        );
        setError("");
        setLoading(false);
      })
      .catch((err) => {
        if (!alive) return;
        const aborted = err?.name === "AbortError" || err?.name === "TimeoutError";
        setError(
          aborted
            ? "New & noted took too long. The lists did not load — try again."
            : humanError(err),
        );
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedList]);

  async function add(item, kind) {
    const key = itemKey(item, kind);
    setBusy(key);
    setError("");
    try {
      await api.addWanted(notedWantedBody(item, kind));
      setSaved((current) => ({ ...current, [key]: true }));
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy("");
    }
  }

  const lanes = payload?.lanes || [];
  const lists = payload?.lists || [];
  const activeLane = lanes.find((lane) => lane.id === activeList) || lanes[0];

  return (
    <div className="admin-room page-settle" data-testid="noted-page">
      <p className="kicker">Beyond the shelves</p>
      <h1>New & noted</h1>
      <p className="lede">
        Trending books, bestseller lists, and what the indexers just posted. Search the shelves, find beyond, or add it to Wanted.
      </p>
      <div className="chip-row" data-testid="noted-lists">
        {lists.map((list) => (
          <button
            key={list.id}
            type="button"
            className={list.id === activeList ? "chip is-current" : "chip"}
            onClick={() => setActiveList(list.id)}
            aria-pressed={list.id === activeList}
          >
            {list.label}
          </button>
        ))}
      </div>
      {error ? <p className="alert">{error}</p> : null}
      {loading ? <WarmLoad message="Warming New & noted…" testId="noted-loading" /> : null}
      {!loading && activeLane
        ? (
            <section key={activeLane.id} className="stack" data-testid={`noted-lane-${activeLane.id}`}>
              <h2>{activeLane.label || activeLane.id}</h2>
              {activeLane.origin_label ? (
                <p className="muted" data-testid="noted-origin">
                  {activeLane.origin_label}
                </p>
              ) : null}
              {activeLane.empty_copy && !activeLane.items?.length ? (
                <p className="empty-note" data-testid={`noted-empty-${activeLane.id}`}>
                  {activeLane.empty_copy}
                </p>
              ) : null}
              <ul className="noted-books">
                {collapseNotedBooks(activeLane.items).map((item) => {
                  const actions = listFormatActions(item);
                  const savedHere = actions.some((action) => saved[itemKey(item, action.kind)]);
                  const status = actions.some((action) => action.owned) || notedBookStatus(item) === "matched"
                    ? "Matched"
                    : savedHere || notedBookStatus(item) === "wanted"
                      ? "Wanted"
                      : "Missing";
                  return (
                    <NotedBookCard
                      key={`${activeLane.id}|${item.key}`}
                      book={item}
                      status={status}
                      weeks={weekCountLabel(item.weekCount)}
                      testId="noted-item"
                    >
                      <Link className="cta outline compact" to={notedSearchHref(item)} data-testid="noted-search">
                        Search the shelves
                      </Link>
                      <Link className="cta outline compact" to={notedFindHref(item)} data-testid="noted-find">
                        Find beyond
                      </Link>
                      {actions.map((action) => {
                        if (action.owned) {
                          return (
                            <span key={action.kind} className="noted-owned">
                              <Link className="cta compact" to={action.href} data-testid={`noted-shelf-${action.kind}`}>
                                On the shelf
                              </Link>
                              {action.readHref ? (
                                <Link
                                  className="cta outline compact"
                                  to={action.readHref}
                                  data-testid={`noted-read-${action.kind}`}
                                >
                                  Read
                                </Link>
                              ) : null}
                              {action.downloadHref ? (
                                <a
                                  className="cta outline compact"
                                  href={action.downloadHref}
                                  data-testid={`noted-download-${action.kind}`}
                                >
                                  Download
                                </a>
                              ) : null}
                              {action.listenHref ? (
                                <Link
                                  className="cta outline compact"
                                  to={action.listenHref}
                                  data-testid={`noted-listen-${action.kind}`}
                                >
                                  Listen
                                </Link>
                              ) : null}
                            </span>
                          );
                        }
                        if (!payload?.can_add) return null;
                        const key = itemKey(item, action.kind);
                        if (saved[key]) return null;
                        return (
                          <button
                            key={action.kind}
                            type="button"
                            className="cta compact"
                            data-testid={`noted-want-${action.kind}`}
                            disabled={busy === key}
                            onClick={() => add(item, action.kind)}
                          >
                            Add to Wanted
                          </button>
                        );
                      })}
                    </NotedBookCard>
                  );
                })}
              </ul>
            </section>
          )
        : null}
    </div>
  );
}
