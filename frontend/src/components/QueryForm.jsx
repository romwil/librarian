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
  kind = "",
  onKindCommit = () => {},
  advanced = {},
  onAdvanced = () => {},
  onSubmit,
  placeholder = "Title, author, or ISBN",
  ariaLabel = "Search",
  kindHelp = FIELD_HELP.searchKind,
  advancedSummary = "More ways to search",
  variant = "search",
  kinds = KINDS,
  showKindChips = true,
  advancedOpen = false,
}) {
  const adv = advanced || { author: "", title: "", isbn: "", series: "", issue: "", artist: "", album: "", year: "" };
  const isFind = variant === "find";
  const isHero = variant === "hero";
  const shown = visibleFindFields(kind);

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

  const qPlaceholder = isFind ? findPlaceholder(kind) || placeholder : placeholder;

  return (
    <form
      role="search"
      className={isHero ? "hero-search-form" : "search-compose"}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="search-hero search-field">
        <span aria-hidden="true">⌕</span>
        <TypeaheadField
          id={inputId}
          field="q"
          kind={kind}
          value={draft}
          placeholder={qPlaceholder}
          ariaLabel={ariaLabel}
          onChange={onDraft}
          onEnterSubmit={() => {
            const form = document.getElementById(inputId)?.form;
            form?.requestSubmit();
          }}
        />
        <kbd>/</kbd>
      </div>
      {!isHero && showKindChips ? (
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
      ) : null}
      {isHero ? null : isFind ? (
        shown.length ? (
          <div className="advanced find-fields" data-testid="find-fields" data-kind={kind || "all"}>
            {shown.map(renderField)}
          </div>
        ) : null
      ) : (
        <details
          className="advanced"
          open={advancedOpen ? true : undefined}
          data-testid="search-advanced"
          data-kind={kind || "all"}
        >
          <summary className="kicker">{advancedSummary}</summary>
          <div className="advanced-fields">
            {showKindChips ? null : (
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
            )}
            {shown.map(renderField)}
          </div>
        </details>
      )}
      {/* Multiple text fields suppress implicit Enter submit; keep one real submit control. */}
      <button type="submit" className={isHero ? "hero-search-submit" : "sr-only"}>
        {isFind ? "Find" : "Search"}
      </button>
    </form>
  );
}
