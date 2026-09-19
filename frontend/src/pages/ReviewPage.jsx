import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import { FIELD_HELP, emptyReviewCopy, humanError } from "../copy.js";
import { requestBodyFromHit } from "../find.js";
import {
  applyBodyFromDraft,
  collisionActionCopy,
  collisionApplyAllowed,
  effectiveReviewReason,
  fieldsFromWork,
  reviewActionsFromWork,
  reviewDiagnosisCopy,
  reviewFindHref,
  reviewReasonCopy,
  unpackStuckWorks,
} from "../review.js";

const KINDS = ["book", "magazine", "comic", "audiobook", "music"];

export default function ReviewPage() {
  const [params] = useSearchParams();
  const focusId = String(params.get("work") || "").trim();
  const [works, setWorks] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState({});
  const [bulkNote, setBulkNote] = useState("");
  const [error, setError] = useState("");
  const [regrabs, setRegrabs] = useState({});
  const [quiet, setQuiet] = useState(null);
  const [quietNote, setQuietNote] = useState("");
  const focusRef = useRef(null);
  const autoRegrabTried = useRef(new Set());

  function reload() {
    api
      .review()
      .then((data) => {
        const next = data.works || [];
        setWorks(next);
        setDrafts((prev) => {
          const merged = { ...prev };
          next.forEach((work) => {
            const base = fieldsFromWork(work);
            const suggested = work.folder_diagnosis?.suggested_folder;
            if (!merged[work.id]) {
              merged[work.id] = {
                ...base,
                folder: base.folder || suggested || "",
              };
            }
          });
          return merged;
        });
      })
      .catch((err) => setError(humanError(err)));
  }

  useEffect(reload, []);

  useEffect(() => {
    api
      .quietHours()
      .then(setQuiet)
      .catch(() => setQuiet(null));
  }, []);

  useEffect(() => {
    if (!focusId || !works.length) return;
    focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, works]);

  async function saveQuiet(patch) {
    setQuietNote("");
    try {
      const next = await api.saveQuietHours({ ...(quiet || {}), ...patch });
      setQuiet(next);
      setQuietNote("Quiet hours saved.");
    } catch (err) {
      setQuietNote(humanError(err));
    }
  }

  function patch(workId, key, value) {
    setDrafts((prev) => ({
      ...prev,
      [workId]: { ...(prev[workId] || {}), [key]: value },
    }));
  }

  function setWorkBusy(workId, on) {
    setBusy((prev) => ({ ...prev, [workId]: on }));
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

  async function repair(work) {
    setWorkBusy(work.id, true);
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    try {
      await api.reviewRepair(work.id);
      reload();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    } finally {
      setWorkBusy(work.id, false);
    }
  }

  async function retry(work) {
    setWorkBusy(work.id, true);
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    try {
      await api.reviewRetry(work.id);
      reload();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    } finally {
      setWorkBusy(work.id, false);
    }
  }

  async function loadRegrab(work) {
    setWorkBusy(work.id, true);
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    try {
      const data = await api.reviewRegrab(work.id);
      setRegrabs((prev) => ({ ...prev, [work.id]: data }));
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    } finally {
      setWorkBusy(work.id, false);
    }
  }

  useEffect(() => {
    for (const work of works) {
      const actions = reviewActionsFromWork(work);
      if (!actions.canRegrab) continue;
      if (autoRegrabTried.current.has(work.id)) continue;
      if (regrabs[work.id]) continue;
      autoRegrabTried.current.add(work.id);
      loadRegrab(work);
    }
    // Auto-fetch once per slip when can_regrab; manual Smart re-grab still refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [works]);

  async function requestRegrab(work, candidate) {
    setWorkBusy(work.id, true);
    setErrors((prev) => ({ ...prev, [work.id]: "" }));
    try {
      // Explicit Request click → existing /api/request path (Confirm for readers; never auto-queue).
      await api.requestItem(
        requestBodyFromHit(candidate, {
          kind: work.kind || candidate.kind || "",
          title: work.title || "",
          author: work.author || "",
        }),
      );
      reload();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [work.id]: humanError(err) }));
    } finally {
      setWorkBusy(work.id, false);
    }
  }

  async function bulkAction(kind) {
    const stuck = unpackStuckWorks(works).filter((work) => {
      const actions = reviewActionsFromWork(work);
      return kind === "repair" ? actions.canRepair : actions.canRetry;
    });
    if (!stuck.length) {
      setBulkNote(kind === "repair" ? "No slips with Repair available." : "No slips ready to Retry.");
      return;
    }
    setBulkNote(`${kind === "repair" ? "Repairing" : "Retrying"} ${stuck.length}…`);
    let ok = 0;
    for (const work of stuck) {
      try {
        if (kind === "repair") await api.reviewRepair(work.id);
        else await api.reviewRetry(work.id);
        ok += 1;
      } catch {
        /* continue */
      }
    }
    setBulkNote(`${ok} of ${stuck.length} ${kind === "repair" ? "repaired" : "retried"}.`);
    reload();
  }

  const unpackCount = unpackStuckWorks(works).length;

  return (
    <div className="admin-room">
      <p className="kicker">Bagging area</p>
      <h1>Review</h1>
      <p className="lede">
        Slips are downloads organize could not finish filing. Happy-path ISBN books never appear here. Apply files a
        ticket once the folder has readable media — Skip dismisses without shelving.
      </p>
      {quiet ? (
        <details className="more-settings" data-testid="review-quiet-hours">
          <summary className="kicker">Quiet hours</summary>
          <p className="muted">
            {quiet.active_now ? "Active now — new unpacks wait for tonight." : "Inactive — Organize runs normally."}
          </p>
          <div className="field field-check">
            <label>
              <input
                type="checkbox"
                checked={Boolean(quiet.quiet_hours_enabled)}
                onChange={(e) => saveQuiet({ quiet_hours_enabled: e.target.checked })}
              />
              Defer unpack / convert
            </label>
          </div>
          <div className="cta-row compact">
            <label className="field">
              <span className="sr-only">Starts</span>
              <input
                value={quiet.quiet_hours_start || "22:00"}
                onChange={(e) => setQuiet({ ...quiet, quiet_hours_start: e.target.value })}
                onBlur={() => saveQuiet({ quiet_hours_start: quiet.quiet_hours_start })}
              />
            </label>
            <label className="field">
              <span className="sr-only">Ends</span>
              <input
                value={quiet.quiet_hours_end || "07:00"}
                onChange={(e) => setQuiet({ ...quiet, quiet_hours_end: e.target.value })}
                onBlur={() => saveQuiet({ quiet_hours_end: quiet.quiet_hours_end })}
              />
            </label>
          </div>
          {quietNote ? <p className="muted">{quietNote}</p> : null}
        </details>
      ) : null}
      {error ? <p className="alert">{error}</p> : null}
      {unpackCount ? (
        <div className="cta-row review-bulk" data-testid="review-bulk">
          <button type="button" className="cta outline compact" onClick={() => bulkAction("repair")}>
            Repair unpack slips
          </button>
          <button type="button" className="cta outline compact" onClick={() => bulkAction("retry")}>
            Retry unpack slips
          </button>
          {bulkNote ? (
            <p className="muted" role="status">
              {bulkNote}
            </p>
          ) : null}
        </div>
      ) : null}
      {!works.length ? (
        <section className="empty-cta review-empty" data-testid="review-empty">
          <p className="empty-illustration" aria-hidden="true">
            <span className="empty-lamp" />
          </p>
          <p className="lede empty-note">{emptyReviewCopy()}</p>
        </section>
      ) : null}
      <ul className="stack">
        {works.map((work) => {
          const draft = drafts[work.id] || fieldsFromWork(work);
          const focused = Boolean(focusId) && work.id === focusId;
          const reason = effectiveReviewReason(work);
          const collision = reason === "collision";
          const canApply = collisionApplyAllowed(reason, draft, work);
          const shelf = work.shelf_work;
          const diagnosis = reviewDiagnosisCopy(work);
          const actions = reviewActionsFromWork(work);
          const findTo = reviewFindHref(work);
          const workBusy = Boolean(busy[work.id]);
          return (
            <li
              key={work.id}
              ref={focused ? focusRef : null}
              className={["card", "ticket", "ticket-enter", focused ? "is-focus" : ""].filter(Boolean).join(" ")}
              data-testid="review-ticket"
              data-work-id={work.id}
              data-focused={focused ? "true" : "false"}
              data-reason={reason || ""}
            >
              <header className="ticket-head">
                <p className="kicker">{focused ? "From Queue" : "Slip"}</p>
                <span className="seal">{draft.kind || work.kind}</span>
              </header>
              <strong className="ticket-title">{draft.title || work.title || "Untitled"}</strong>
              {actions.quietHours ? (
                <p className="chip is-on" data-testid="quiet-hours-chip">
                  Queued for tonight
                </p>
              ) : null}
              <p className="lede" data-testid="review-reason-copy">
                {reviewReasonCopy(reason)}
              </p>
              <details className="ticket-diagnosis" data-testid="review-diagnosis">
                <summary>About this slip</summary>
                <div className="empty-note">
                  <p>
                    <strong>What this slip means.</strong> {diagnosis.meaning}
                  </p>
                  <p>
                    <strong>What we tried.</strong> {diagnosis.tried}
                  </p>
                  <p>
                    <strong>What’s wrong.</strong> {diagnosis.whatsWrong}
                  </p>
                  <p>
                    <strong>What to do.</strong> {diagnosis.nextSteps}
                  </p>
                  {diagnosis.pathNote ? (
                    <p data-testid="review-path-note">
                      <strong>About this path.</strong> {diagnosis.pathNote}
                    </p>
                  ) : null}
                  {diagnosis.suggestedFolder ? (
                    <p data-testid="review-suggested-folder">
                      <strong>Suggested folder.</strong>{" "}
                      <code className="font-mono">{diagnosis.suggestedFolder}</code>{" "}
                      <button
                        type="button"
                        className="cta ghost compact"
                        onClick={() => patch(work.id, "folder", diagnosis.suggestedFolder)}
                      >
                        Use this path
                      </button>
                    </p>
                  ) : null}
                </div>
              </details>
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
              {(actions.canRepair || actions.canRetry || actions.canRequestNew || actions.canRegrab) && (
                <div className="cta-row ticket-recovery" data-testid="review-recovery">
                  {actions.canRepair ? (
                    <button
                      type="button"
                      className="cta compact"
                      disabled={workBusy}
                      onClick={() => repair(work)}
                      data-testid="review-repair"
                    >
                      Repair
                    </button>
                  ) : null}
                  {actions.canRetry ? (
                    <button
                      type="button"
                      className={`cta compact${actions.canRepair ? " outline" : ""}`}
                      disabled={workBusy}
                      onClick={() => retry(work)}
                      data-testid="review-retry"
                    >
                      Retry
                    </button>
                  ) : null}
                  {actions.canRegrab ? (
                    <button
                      type="button"
                      className="cta outline compact"
                      disabled={workBusy}
                      onClick={() => loadRegrab(work)}
                      data-testid="review-regrab"
                    >
                      Smart re-grab
                    </button>
                  ) : null}
                  {actions.canRequestNew ? (
                    <Link
                      className="cta outline compact"
                      to={findTo}
                      data-testid="review-request-new"
                    >
                      Request new version
                    </Link>
                  ) : null}
                </div>
              )}
              {regrabs[work.id]?.candidates?.length ? (
                <ul className="regrab-list" data-testid="regrab-candidates">
                  {regrabs[work.id].candidates.map((candidate, index) => (
                    <li key={candidate.guid || candidate.title}>
                      <span>{candidate.diff || candidate.title}</span>
                      <button
                        type="button"
                        className={index === 0 ? "cta compact" : "cta compact outline"}
                        disabled={workBusy}
                        onClick={() => requestRegrab(work, candidate)}
                        data-testid="regrab-request"
                      >
                        Request this
                      </button>
                    </li>
                  ))}
                </ul>
              ) : regrabs[work.id]?.ready && !regrabs[work.id]?.candidates?.length ? (
                <p className="muted" data-testid="regrab-empty">
                  No alternate releases yet — try Request new version on Find.
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
                    disabled={!canApply || workBusy}
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
