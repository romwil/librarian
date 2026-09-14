import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";

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
  if (!data) return <p className="lede" style={{ padding: "var(--space-8) var(--gutter)" }}>Opening the volume…</p>;

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
    <article>
      <section className="work-hero">
        <div className="work-hero-art" aria-hidden="true" />
        <div className="work-hero-scrim" aria-hidden="true" />
        <div className="work-hero-inner">
          <div className="chip-row" style={{ marginBottom: 16 }}>
            {work.kind ? <span className="chip is-on">{work.kind}</span> : null}
            {work.year ? <span className="chip">{work.year}</span> : null}
            {work.author ? <span className="chip">{work.author}</span> : null}
            {work.isbn ? <span className="chip font-mono">{work.isbn}</span> : null}
            {data.favorite ? <span className="chip is-on">Favorites</span> : null}
          </div>
          <h1>{work.title}</h1>
          <p className="work-sub">{[work.author, work.year, work.series_name, work.series_index].filter(Boolean).join(" · ")}</p>
          <div className="cta-row">
            <button type="button" className="cta outline" onClick={favorite}>
              {data.favorite ? "In Favorites" : "Favorite"}
            </button>
            {op && work.kind === "music" && work.music_state === "incoming" ? (
              <button type="button" className="cta ghost" onClick={promote}>
                Promote to Plexamp
              </button>
            ) : null}
            <Link className="cta ghost" to="/">
              Back to The Hall
            </Link>
          </div>
        </div>
      </section>
      <div className="work-body">
        {work.description ? (
          <section className="synopsis">
            <h2>Description</h2>
            <p>{work.description}</p>
          </section>
        ) : null}
        {data.files?.length ? (
          <section>
            <h2 className="kicker">Files</h2>
            <ul className="file-list">
              {data.files.map((file) => (
                <li key={file.id}>{file.filename}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
      <Rail title={work.author ? `More by ${work.author}` : "More on this shelf"} items={data.related} />
    </article>
  );
}
