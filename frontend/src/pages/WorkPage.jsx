import { useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { api } from "../api.js";

export default function WorkPage() {
  const { id } = useParams();
  const { user } = useOutletContext();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .work(id)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [id]);

  if (error) return <p className="alert">{error}</p>;
  if (!data) return <p className="muted">Opening the volume…</p>;

  const work = data.work;
  const op = user.role === "owner" || user.role === "op";

  async function favorite() {
    const next = await api.favorite(work.id);
    setData({ ...data, favorite: next.favorite });
  }

  async function promote() {
    const next = await api.promote(work.id);
    setData({ ...data, work: next.work });
  }

  return (
    <article className="work-hero">
      <p className="eyebrow">{work.kind}</p>
      <h1>{work.title}</h1>
      <p className="lede">
        {[work.author, work.series_name, work.series_index, work.year].filter(Boolean).join(" · ")}
      </p>
      {work.description ? <p>{work.description}</p> : null}
      <div className="peek-acts">
        <button type="button" className="primary" onClick={favorite}>
          {data.favorite ? "In Favorites" : "Favorite"}
        </button>
        {op && work.kind === "music" && work.music_state === "incoming" ? (
          <button type="button" className="ghost" onClick={promote}>
            Promote to Plexamp
          </button>
        ) : null}
      </div>
      {data.files?.length ? (
        <ul className="file-list">
          {data.files.map((file) => (
            <li key={file.id}>{file.filename}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
