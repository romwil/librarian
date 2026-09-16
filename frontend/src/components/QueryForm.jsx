import { FieldLabel } from "./FieldHelp.jsx";
import TypeaheadField, { isTypeaheadField } from "./TypeaheadField.jsx";
import { FIELD_HELP } from "../copy.js";
import { KINDS, findPlaceholder, visibleFindFields } from "../find.js";

const FIELD_META = {
  author: { label: "Author", help: "searchAuthor" },
  title: { label: "Title", help: "searchTitle" },
  isbn: { label: "ISBN", help: "searchIsbn", mono: true },
  series: { label: "Series", help: "searchSeries" },
  issue: { label: "Issue", help: "searchIssue" },
  artist: { label: "Artist", help: "searchArtist" },
  album: { label: "Album", help: "searchAlbum" },
  year: { label: "Year", help: "searchYear" },
};

export default function QueryForm({
  inputId = "hall-search",
  draft,
  onDraft,
  kind,
  onKindCommit,
  advanced,
  onAdvanced,
  onSubmit,
  placeholder,
  ariaLabel = "Search",
  kindHelp = FIELD_HELP.searchKind,
  advancedSummary = "Advanced",
  variant = "search",
  kinds = KINDS,
}) {
  const adv = advanced || { author: "", title: "", isbn: "", series: "", issue: "", artist: "", album: "", year: "" };
  const isFind = variant === "find";
  const shown = visibleFindFields(kind);
  const hasAdvanced = shown.some((key) => adv[key]);

  function renderField(key) {
    const meta = FIELD_META[key];
    if (!meta) return null;
    const fieldId = `${inputId}-${key}`;
    const setValue = (next) => onAdvanced({ ...adv, [key]: next });
    return (
      <div className="field" key={key}>
        <FieldLabel htmlFor={fieldId} label={meta.label} help={FIELD_HELP[meta.help]} />
        {isTypeaheadField(key) ? (
          <TypeaheadField
            id={fieldId}
            field={key}
            kind={kind}
            value={adv[key] || ""}
            className={meta.mono ? "font-mono" : undefined}
            onChange={setValue}
            onEnterSubmit={() => {
              const form = document.getElementById(fieldId)?.form;
              form?.requestSubmit();
            }}
          />
        ) : (
          <input
            id={fieldId}
            className={meta.mono ? "font-mono" : undefined}
            value={adv[key] || ""}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
        )}
      </div>
    );
  }

  return (
    <form
      className="search-compose"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="search-hero search-field">
        <span aria-hidden="true">⌕</span>
        <input
          id={inputId}
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder={isFind ? findPlaceholder(kind) || placeholder : placeholder}
          aria-label={ariaLabel}
        />
        <kbd>/</kbd>
      </div>
      <div className="search-hero chip-row search-compose-chips">
        {kinds.map(([value, label]) => (
          <button
            key={value || "all"}
            type="button"
            className={`chip${kind === value ? " is-on" : ""}`}
            aria-pressed={kind === value}
            onClick={() => onKindCommit(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {isFind ? (
        shown.length ? (
          <div className="advanced find-fields" data-testid="find-fields" data-kind={kind || "all"}>
            {shown.map(renderField)}
          </div>
        ) : null
      ) : (
        <details className="advanced" defaultOpen={hasAdvanced} data-testid="search-advanced" data-kind={kind || "all"}>
          <summary className="kicker">{advancedSummary}</summary>
          <div className="advanced-fields">
            <div className="field">
              <FieldLabel htmlFor={`${inputId}-kind`} label="Kind" help={kindHelp} />
              <select id={`${inputId}-kind`} value={kind} onChange={(e) => onKindCommit(e.target.value)}>
                {kinds.map(([value, label]) => (
                  <option key={value || "any"} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {shown.map(renderField)}
          </div>
        </details>
      )}
      {/* Multiple text fields suppress implicit Enter submit; keep one real submit control. */}
      <button type="submit" className="sr-only">
        {isFind ? "Find" : "Search the stacks"}
      </button>
    </form>
  );
}
