import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function ReviewPage() {
  const [works, setWorks] = useState([]);
  const [error, setError] = useState("");

  function reload() {
    api
      .review()
      .then((data) => setWorks(data.works || []))
      .catch((err) => setError(err.message));
  }

  useEffect(reload, []);

  async function apply(work) {
    await api.reviewApply(work.id, {
      title: work.title,
      author: work.author,
      kind: work.kind,
      series_name: work.series_name,
      series_index: work.series_index,
      folder: work.folder_path,
    });
    reload();
  }

  async function skip(work) {
    await api.reviewSkip(work.id);
    reload();
  }

  return (
    <div className="admin-room">
      <p className="eyebrow">Bag</p>
      <h1>Review</h1>
      <p className="lede">Unexpected items only. Happy-path ISBN books never appear here.</p>
      {error ? <p className="alert">{error}</p> : null}
      {!works.length ? <p className="muted">The bag is empty.</p> : null}
      <ul className="stack">
        {works.map((work) => (
          <li key={work.id} className="card">
            <strong>{work.title}</strong>
            <p className="muted">
              {work.review_reason} · {work.kind}
            </p>
            <div className="peek-acts">
              <button type="button" className="primary" onClick={() => apply(work)}>
                Apply
              </button>
              <button type="button" className="ghost" onClick={() => skip(work)}>
                Skip
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
