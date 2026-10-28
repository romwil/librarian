import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";

const DEFAULT_LIST = "hardcover-fiction";

function sixMonthsAgo() {
  const day = new Date();
  day.setMonth(day.getMonth() - 6);
  return day.toISOString().slice(0, 10);
}

export default function NotedHistoryPage() {
  const { user } = useOutletContext() || {};
  const [listName, setListName] = useState(DEFAULT_LIST);
  const [start, setStart] = useState(sixMonthsAgo);
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [history, setHistory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  if (user?.role !== "owner") return null;

  async function load() {
    setBusy(true);
    setNote("");
    try {
      setHistory(await api.notedHistory({ listName, start, end }));
    } catch (error) {
      setHistory(null);
      setNote(humanError(error));
    } finally {
      setBusy(false);
    }
  }

  async function addMissing() {
    if (!history) return;
    setBusy(true);
    try {
      const result = await api.addMissingNotedHistory(history.items);
      setNote(`Added ${Number(result?.added || 0)} missing title${Number(result?.added || 0) === 1 ? "" : "s"} to Wanted.`);
      setHistory(await api.notedHistory({ listName, start, end }));
    } catch (error) {
      setNote(humanError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-room page-settle" data-testid="noted-history-page">
      <p className="kicker">Owner</p>
      <h1>New &amp; noted history</h1>
      <p className="lede">Fetch a New York Times category once per week, then review the distinct titles from the selected range.</p>
      <div className="cta-row">
        <label className="field">NYT category
          <input aria-label="NYT category" value={listName} onChange={(event) => setListName(event.target.value)} />
        </label>
        <label className="field">Start
          <input aria-label="Start date" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="field">End
          <input aria-label="End date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
        <button type="button" className="cta outline" disabled={busy} onClick={load}>Load range</button>
      </div>
      {history ? (
        <>
          <div className="cta-row">
            <button type="button" className="cta" disabled={busy} onClick={addMissing}>Add missing</button>
          </div>
          <ul className="stack">
            {history.items.map((item) => (
              <li className="card" key={item.isbn13 || `${item.title}|${item.author}`}>
                <strong>{item.title}</strong>
                {item.author ? <p className="muted">{item.author}</p> : null}
                <p className="muted">{item.weeks.join(", ")} · {item.shelved ? "On the shelf" : "Not on the shelf"}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {note ? <p className="muted" role="status">{note}</p> : null}
    </div>
  );
}
