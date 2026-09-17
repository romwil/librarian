import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import { FIELD_HELP, emptyReviewCopy, humanError } from "../copy.js";
import {
  applyBodyFromDraft,
  collisionActionCopy,
  collisionApplyAllowed,
  fieldsFromWork,
  reviewReasonCopy,
} from "../review.js";

const KINDS = ["book", "magazine", "comic", "audiobook", "music"];

export default function ReviewPage() {
  const [params] = useSearchParams();
  const focusId = String(params.get("work") || "").trim();
  const [works, setWorks] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const focusRef = useRef(null);

  function reload() {
    api
      .review()
      .then((data) => {
        const next = data.works || [];
        setWorks(next);
        setDrafts((prev) => {
          const merged = { ...prev };
          next.forEach((work) => {
            merged[work.id] = merged[work.id] || fieldsFromWork(work);
          });
          return merged;
        });
      })
      .catch((err) => setError(humanError(err)));
  }

  useEffect(reload, []);

  useEffect(() => {
    if (!focusId || !works.length) return;
    focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, works]);

  function patch(workId, key, value) {
    setDrafts((prev) => ({
      ...prev,
      [workId]: { ...(prev[workId] || {}), [key]: value },
    }));
  }

  async function apply(work) {
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    try {
      await api.reviewApply(work.id, applyBodyFromDraft(drafts[work.id] || fieldsFromWork(work)));
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[work.id];
        return next;
      });
      reload();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    }
  }

  async function skip(work) {
    try {
      await api.reviewSkip(work.id);
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[work.id];
        return next;
      });
      reload();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    }
  }

  return (
    <div className="admin-room">
      <p className="kicker">Bagging area</p>
      <h1>Review</h1>
      <p className="lede">Unexpected items only. Happy-path ISBN books never appear here. Apply files a ticket, not a dump.</p>
      {error ? <p className="alert">{error}</p> : null}
      {!works.length ? <p className="empty-note">{emptyReviewCopy()}</p> : null}
      <ul className="stack">
        {works.map((work) => {
          const draft = drafts[work.id] || fieldsFromWork(work);
          const focused = Boolean(focusId) && work.id === focusId;
          const collision = work.review_reason === "collision";
          const canApply = collisionApplyAllowed(work.review_reason, draft, work);
          const shelf = work.shelf_work;
          return (
            <li
              key={work.id}
              ref={focused ? focusRef : null}
              className={["card", "ticket", focused ? "is-focus" : ""].filter(Boolean).join(" ")}
              data-testid="review-ticket"
              data-work-id={work.id}
              data-focused={focused ? "true" : "false"}
              data-reason={work.review_reason || ""}
            >
              <header className="ticket-head">
                <p className="kicker">{focused ? "From Queue" : "Slip"}</p>
                <span className="seal">{draft.kind || work.kind}</span>
              </header>
              <strong className="ticket-title">{draft.title || work.title || "Untitled"}</strong>
              <p className="lede">{reviewReasonCopy(work.review_reason)}</p>
              {collision ? (
                <p className="empty-note" data-testid="collision-action-copy">
                  {collisionActionCopy()}
                </p>
              ) : null}
              {shelf?.id ? (
                <p className="muted" data-testid="collision-shelf-link">
                  Already cataloged:{" "}
                  <Link to={`/works/${encodeURIComponent(shelf.id)}`}>
                    {shelf.title || "Open on Hall"}
                    {shelf.author ? ` — ${shelf.author}` : ""}
                  </Link>
                </p>
              ) : null}
              <form
                className="identify-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!canApply) return;
                  apply(work);
                }}
              >
                <div className="field">
                  <FieldLabel htmlFor={`kind-${work.id}`} label="Kind" help={FIELD_HELP.reviewKind} />
                  <select
                    id={`kind-${work.id}`}
                    value={draft.kind}
                    onChange={(e) => patch(work.id, "kind", e.target.value)}
                  >
                    {KINDS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`title-${work.id}`} label="Title" help={FIELD_HELP.reviewTitle} />
                  <input
                    id={`title-${work.id}`}
                    value={draft.title}
                    onChange={(e) => patch(work.id, "title", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`author-${work.id}`} label="Author" help={FIELD_HELP.reviewAuthor} />
                  <input
                    id={`author-${work.id}`}
                    value={draft.author}
                    onChange={(e) => patch(work.id, "author", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`isbn-${work.id}`} label="ISBN" help={FIELD_HELP.reviewIsbn} />
                  <input
                    id={`isbn-${work.id}`}
                    className="font-mono"
                    value={draft.isbn}
                    onChange={(e) => patch(work.id, "isbn", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`series-${work.id}`} label="Series" help={FIELD_HELP.reviewSeries} />
                  <input
                    id={`series-${work.id}`}
                    value={draft.series_name}
                    onChange={(e) => patch(work.id, "series_name", e.target.value)}
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor={`index-${work.id}`} label="Issue / index" help={FIELD_HELP.reviewIndex} />
                  <input
                    id={`index-${work.id}`}
                    value={draft.series_index}
                    onChange={(e) => patch(work.id, "series_index", e.target.value)}
                  />
                </div>
                <div className="field field-wide">
                  <FieldLabel htmlFor={`folder-${work.id}`} label="Complete folder" help={FIELD_HELP.reviewFolder} />
                  <input
                    id={`folder-${work.id}`}
                    value={draft.folder}
                    onChange={(e) => patch(work.id, "folder", e.target.value)}
                    placeholder="Path this Librarian process can read"
                  />
                </div>
                {errors[work.id] ? <p className="alert field-wide">{errors[work.id]}</p> : null}
                <div className="cta-row field-wide">
                  <button
                    type="submit"
                    className="cta"
                    disabled={!canApply}
                    title={
                      collision && !canApply
                        ? "Change title, author, series, or folder so the destination is free — Apply will not overwrite."
                        : undefined
                    }
                    data-testid="review-apply"
                  >
                    Apply
                  </button>
                  <button type="button" className="cta ghost" onClick={() => skip(work)} data-testid="review-skip">
                    Skip
                  </button>
                </div>
              </form>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
