import { FieldLabel } from "./FieldHelp.jsx";
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
  advancedSummary = "Advanced — same page, not a different site",
  variant = "search",
  kinds = KINDS,
}) {
  const adv = advanced || { author: "", title: "", isbn: "", series: "", issue: "", artist: "", album: "", year: "" };
  const isFind = variant === "find";
  const morphFields = isFind ? visibleFindFields(kind) : ["author", "title", "isbn", "series", "year"];
  const hasAdvanced = morphFields.some((key) => adv[key]);
  const shown = isFind ? morphFields : ["author", "title", "isbn", "series", "year"];

  function renderField(key) {
    const meta = FIELD_META[key];
    if (!meta) return null;
    return (
      <div className="field" key={key}>
        <FieldLabel htmlFor={`${inputId}-${key}`} label={meta.label} help={FIELD_HELP[meta.help]} />
        <input
          id={`${inputId}-${key}`}
          className={meta.mono ? "font-mono" : undefined}
          value={adv[key] || ""}
          onChange={(e) => onAdvanced({ ...adv, [key]: e.target.value })}
        />
      </div>
    );
  }

  return (
    <>
      <form
        className="search-hero search-field"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <span aria-hidden="true">⌕</span>
        <input
          id={inputId}
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder={isFind ? findPlaceholder(kind) || placeholder : placeholder}
          aria-label={ariaLabel}
        />
        <kbd>/</kbd>
      </form>
      <div className="search-hero chip-row" style={{ justifyContent: "center", marginBottom: 12 }}>
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
        <details className="advanced" defaultOpen={hasAdvanced}>
          <summary className="kicker">{advancedSummary}</summary>
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
        </details>
      )}
    </>
  );
}
