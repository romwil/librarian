import { Link } from "react-router-dom";
import { FIELD_HELP, SLIP_ACTION_HELP, humanError } from "../copy.js";
import { ThinkingButton } from "./Thinking.jsx";
import FieldHelp, { FieldLabel } from "./FieldHelp.jsx";
import SearchTraceDisclosure from "./SearchTraceDisclosure.jsx";
import {
  collisionActionCopy,
  collisionApplyAllowed,
  effectiveReviewReason,
  holdSlipReasonWords,
  recommendedMotionCtaClass,
  recommendedMotionLabel,
  reviewActionsFromWork,
  reviewDiagnosisCopy,
  reviewReasonCopy,
  slipTriage,
} from "../review.js";

const KINDS = ["book", "magazine", "comic", "audiobook", "music"];

/** One hold slip: the one-line ticket and the More card underneath. */
export default function HoldSlipCard({
  work,
  draft,
  focused,
  focusRef,
  busyValue,
  slipError,
  statusNote,
  matchBag,
  regrab,
  onPatch,
  onPrimary,
  onApply,
  onSkip,
  onRepair,
  onRetry,
  onRetrieve,
  onSuggest,
  onApplyAuthority,
  onRequestCandidate,
  onUseListedMatch,
}) {
  const reason = effectiveReviewReason(work);
  const collision = reason === "collision";
  const canApply = collisionApplyAllowed(reason, draft, work);
  const shelf = work.shelf_work;
  const diagnosis = reviewDiagnosisCopy(work);
  const actions = reviewActionsFromWork(work);
  const triage = slipTriage(work);
  const workBusy = Boolean(busyValue);
  const activeAction = typeof busyValue === "string" ? busyValue : "";
  const visibleNote = statusNote && statusNote !== slipError ? statusNote : "";
  const primaryLabel = recommendedMotionLabel(actions.recommendedMotion);

  return (
    <li
      ref={focused ? focusRef : null}
      className={["card", "ticket", "hold-slip", "ticket-enter", focused ? "is-focus" : ""].filter(Boolean).join(" ")}
      data-testid="hold-slip"
      data-work-id={work.id}
      data-focused={focused ? "true" : "false"}
      data-reason={reason || ""}
      aria-busy={workBusy || undefined}
    >
      <div className="hold-slip-line" data-testid="hold-slip-line">
        <strong className="ticket-title">{draft.title || work.title || "Untitled"}</strong>
        <span className="muted hold-slip-reason" data-testid="review-reason-copy">
          {holdSlipReasonWords(work)}
        </span>
        <ThinkingButton
          type="button"
          className="cta compact"
          data-testid="hold-slip-primary"
          busy={workBusy}
          disabled={!workBusy && actions.recommendedMotion === "apply" && !canApply}
          onClick={() => onPrimary()}
        >
          {primaryLabel}
        </ThinkingButton>
      </div>
      <details className="ticket-diagnosis" data-testid="hold-slip-more" open={focused || undefined}>
        <summary>More</summary>
        <header className="ticket-head">
          <p className="kicker">{focused ? "From Queue" : "Slip"}</p>
          <span className="seal">{draft.kind || work.kind}</span>
        </header>
        {actions.recommendedMotion ? (
          <p className="chip is-on" data-testid="hold-slip-recommended">
            Recommended: {recommendedMotionLabel(actions.recommendedMotion)}
          </p>
        ) : null}
        {triage ? (
          <p className="chip" data-testid="hold-slip-triage" data-outcome={triage.outcome}>
            Model: {triage.label}
          </p>
        ) : null}
        {triage?.explanation ? (
          <p className="muted" data-testid="hold-slip-triage-why">
            {triage.explanation}
          </p>
        ) : null}
        {work.owner_decision_note ? (
          <p className="muted" data-testid="hold-slip-owner-note">
            {work.owner_decision_note}
          </p>
        ) : null}
        {actions.quietHours ? (
          <p className="chip is-on" data-testid="quiet-hours-chip">
            Queued for tonight
          </p>
        ) : null}
        <details className="ticket-diagnosis" data-testid="review-diagnosis">
          <summary>About this slip</summary>
          <div className="empty-note">
            <p>
              <strong>What this slip means.</strong> {diagnosis.meaning}
            </p>
            <p>
              <strong>What we tried.</strong> {diagnosis.tried}
            </p>
            {diagnosis.whatsWrong && diagnosis.whatsWrong !== reviewReasonCopy(reason, work.folder_diagnosis || {}) ? (
              <p>
                <strong>What’s wrong.</strong> {diagnosis.whatsWrong}
              </p>
            ) : null}
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
                <strong>Suggested folder.</strong> <code className="font-mono">{diagnosis.suggestedFolder}</code>{" "}
                <button
                  type="button"
                  className="cta ghost compact"
                  onClick={() => onPatch("folder", diagnosis.suggestedFolder)}
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
        {Array.isArray(work.match_candidates) && work.match_candidates.length ? (
          <div className="match-candidates" data-testid="review-match-candidates">
            <p className="kicker">Match candidates</p>
            <ul className="match-candidate-list">
              {work.match_candidates.map((row) => (
                <li key={row.match_key || `${row.title}-${row.series_name}`}>
                  <div>
                    <strong>{row.title || row.series_name}</strong>
                    <span className="muted">
                      {[
                        row.series_name,
                        row.series_index ? `#${row.series_index}` : "",
                        row.volume_year || row.year,
                        row.publisher,
                        row.match_confidence != null ? `${Math.round(Number(row.match_confidence) * 100)}%` : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                  <ThinkingButton
                    type="button"
                    className="cta outline compact"
                    busy={activeAction === "match"}
                    disabled={workBusy && activeAction !== "match"}
                    data-testid="review-apply-match"
                    onClick={() => onUseListedMatch(row)}
                  >
                    Use this
                  </ThinkingButton>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {(actions.canRepair ||
          actions.canRetry ||
          actions.canRequestNew ||
          actions.canRegrab ||
          actions.canSuggestLlm) && (
          <div className="cta-row ticket-recovery" data-testid="review-recovery">
            {actions.canSuggestLlm ? (
              <ThinkingButton
                type="button"
                className={recommendedMotionCtaClass(work, "suggest")}
                busy={activeAction === "suggest"}
                disabled={workBusy && activeAction !== "suggest"}
                onClick={() => onSuggest()}
                data-testid="review-suggest-llm"
              >
                Suggest with LLM
              </ThinkingButton>
            ) : null}
            {actions.canRepair ? (
              <span className="cta-help">
                <ThinkingButton
                  type="button"
                  className={recommendedMotionCtaClass(work, "repair")}
                  busy={activeAction === "repair"}
                  disabled={workBusy && activeAction !== "repair"}
                  onClick={() => onRepair()}
                  data-testid="review-repair"
                >
                  Repair
                </ThinkingButton>
                <FieldHelp label="Repair">{SLIP_ACTION_HELP.repair}</FieldHelp>
              </span>
            ) : null}
            {actions.canRetry ? (
              <span className="cta-help">
                <ThinkingButton
                  type="button"
                  className={recommendedMotionCtaClass(work, "retry")}
                  busy={activeAction === "retry"}
                  disabled={workBusy && activeAction !== "retry"}
                  onClick={() => onRetry()}
                  data-testid="review-retry"
                >
                  Retry
                </ThinkingButton>
                <FieldHelp label="Retry">{SLIP_ACTION_HELP.retry}</FieldHelp>
              </span>
            ) : null}
            {actions.canRegrab ? (
              <span className="cta-help">
                <ThinkingButton
                  type="button"
                  className={recommendedMotionCtaClass(work, "regrab")}
                  busy={activeAction === "regrab"}
                  disabled={workBusy && activeAction !== "regrab"}
                  onClick={() => onRetrieve("regrab")}
                  data-testid="review-regrab"
                >
                  Smart re-grab
                </ThinkingButton>
                <FieldHelp label="Smart re-grab">{SLIP_ACTION_HELP.regrab}</FieldHelp>
              </span>
            ) : null}
            {actions.canRequestNew ? (
              <span className="cta-help">
                <ThinkingButton
                  type="button"
                  className={recommendedMotionCtaClass(work, "request_new")}
                  busy={activeAction === "requestNew"}
                  disabled={workBusy && activeAction !== "requestNew"}
                  onClick={() => onRetrieve("new_version")}
                  data-testid="review-request-new"
                >
                  Request new version
                </ThinkingButton>
                <FieldHelp label="Request new version">{SLIP_ACTION_HELP.requestNew}</FieldHelp>
              </span>
            ) : null}
          </div>
        )}
        {visibleNote ? (
          <p className="muted" data-testid="review-action-note" role="status">
            {visibleNote}
          </p>
        ) : null}
        {matchBag?.candidates?.length ? (
          <ul className="regrab-list" data-testid="authority-match-candidates">
            {matchBag.candidates.map((candidate, index) => (
              <li key={candidate.match_key || candidate.asin || candidate.title || index}>
                <span>
                  {candidate.title || "Untitled"}
                  {candidate.author ? ` — ${candidate.author}` : ""}
                  {candidate.asin ? ` · ${candidate.asin}` : ""}
                  {candidate.score != null || candidate.match_confidence != null
                    ? ` · ${Math.round(Number(candidate.score ?? candidate.match_confidence) * 100)}%`
                    : ""}
                </span>
                <ThinkingButton
                  type="button"
                  className={index === 0 ? "cta compact" : "cta compact outline"}
                  busy={activeAction === "applyMatch"}
                  disabled={workBusy && activeAction !== "applyMatch"}
                  onClick={() => onApplyAuthority(candidate)}
                  data-testid="authority-match-apply"
                >
                  Use this match
                </ThinkingButton>
              </li>
            ))}
          </ul>
        ) : null}
        {regrab?.beyond_error ? (
          <p className="muted" role="status" data-testid="regrab-beyond-error">
            {humanError(regrab.beyond_error)}
          </p>
        ) : null}
        {regrab?.search_trace || regrab?.remembered_candidates?.length ? (
          <SearchTraceDisclosure
            conversation={regrab?.search_trace?.conversation || []}
            steps={regrab?.search_trace?.steps || []}
            results={regrab?.search_trace?.results || []}
            candidates={regrab?.remembered_candidates || regrab?.candidates || []}
            rankMethod={regrab?.rank_method || ""}
            rankReason={regrab?.rank_reason || ""}
            testId={`regrab-trace-${work.id}`}
          />
        ) : null}
        {regrab?.candidates?.length ? (
          <ul className="regrab-list" data-testid="regrab-candidates">
            {regrab.candidates.map((candidate, index) => (
              <li key={candidate.guid || candidate.title}>
                <span>{candidate.diff || candidate.title}</span>
                {regrab?.queued || regrab?.already_active ? null : (
                  <ThinkingButton
                    type="button"
                    className={index === 0 ? "cta compact" : "cta compact outline"}
                    busy={activeAction === "request"}
                    disabled={workBusy && activeAction !== "request"}
                    onClick={() => onRequestCandidate(candidate)}
                    data-testid="regrab-request"
                  >
                    Request this
                  </ThinkingButton>
                )}
              </li>
            ))}
          </ul>
        ) : regrab?.searched && !regrab?.candidates?.length ? (
          <p className="muted" data-testid="regrab-empty">
            {regrab.note || "No other release turned up for this slip."}
          </p>
        ) : null}
        <form
          className="identify-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canApply) return;
            onApply();
          }}
        >
          <div className="field">
            <FieldLabel htmlFor={`kind-${work.id}`} label="Kind" help={FIELD_HELP.reviewKind} />
            <select id={`kind-${work.id}`} value={draft.kind} onChange={(e) => onPatch("kind", e.target.value)}>
              {KINDS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <FieldLabel htmlFor={`title-${work.id}`} label="Title" help={FIELD_HELP.reviewTitle} />
            <input id={`title-${work.id}`} value={draft.title} onChange={(e) => onPatch("title", e.target.value)} />
          </div>
          <div className="field">
            <FieldLabel htmlFor={`author-${work.id}`} label="Author" help={FIELD_HELP.reviewAuthor} />
            <input id={`author-${work.id}`} value={draft.author} onChange={(e) => onPatch("author", e.target.value)} />
          </div>
          <div className="field">
            <FieldLabel htmlFor={`isbn-${work.id}`} label="ISBN" help={FIELD_HELP.reviewIsbn} />
            <input
              id={`isbn-${work.id}`}
              className="font-mono"
              value={draft.isbn}
              onChange={(e) => onPatch("isbn", e.target.value)}
            />
          </div>
          <div className="field">
            <FieldLabel htmlFor={`series-${work.id}`} label="Series" help={FIELD_HELP.reviewSeries} />
            <input
              id={`series-${work.id}`}
              value={draft.series_name}
              onChange={(e) => onPatch("series_name", e.target.value)}
            />
          </div>
          <div className="field">
            <FieldLabel htmlFor={`index-${work.id}`} label="Issue / index" help={FIELD_HELP.reviewIndex} />
            <input
              id={`index-${work.id}`}
              value={draft.series_index}
              onChange={(e) => onPatch("series_index", e.target.value)}
            />
          </div>
          <div className="field field-wide">
            <FieldLabel htmlFor={`folder-${work.id}`} label="Complete folder" help={FIELD_HELP.reviewFolder} />
            <input
              id={`folder-${work.id}`}
              value={draft.folder}
              onChange={(e) => onPatch("folder", e.target.value)}
              placeholder="Path this Librarian process can read"
            />
          </div>
          {slipError ? <p className="alert field-wide">{slipError}</p> : null}
          <div className="cta-row field-wide">
            <span className="cta-help">
              <ThinkingButton
                type="submit"
                className={recommendedMotionCtaClass(work, "apply", { compact: false })}
                busy={activeAction === "apply"}
                disabled={!canApply || (workBusy && activeAction !== "apply")}
                title={
                  collision && !canApply
                    ? "Change title, author, series, or folder so the destination is free — Apply will not overwrite."
                    : undefined
                }
                data-testid="review-apply"
              >
                Apply
              </ThinkingButton>
              <FieldHelp label="Apply">{SLIP_ACTION_HELP.apply}</FieldHelp>
            </span>
            <span className="cta-help">
              <ThinkingButton
                type="button"
                className={
                  actions.recommendedMotion === "skip"
                    ? recommendedMotionCtaClass(work, "skip", { compact: false })
                    : "cta ghost"
                }
                busy={activeAction === "skip"}
                disabled={workBusy && activeAction !== "skip"}
                onClick={() => onSkip()}
                data-testid="review-skip"
              >
                Skip
              </ThinkingButton>
              <FieldHelp label="Skip">{SLIP_ACTION_HELP.skip}</FieldHelp>
            </span>
          </div>
        </form>
      </details>
    </li>
  );
}
