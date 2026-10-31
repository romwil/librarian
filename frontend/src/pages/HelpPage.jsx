import { useOutletContext } from "react-router-dom";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import { PAGE_TITLE_HELP } from "../copy.js";
import { glossaryForRole } from "../copy/glossary.js";

export default function HelpPage() {
  const { user } = useOutletContext() || {};
  const role = user?.role || "reader";
  const terms = glossaryForRole(role);
  useDocumentTitle(PAGE_TITLE_HELP);

  return (
    <div className="hall page-settle" data-testid="help-page">
      <header className="browse-hero">
        <p className="kicker">Help</p>
        <h1>Words the house uses</h1>
        <p className="lede">
          One name per thing. Ask the house is how a reader requests a missing title. Keepers still confirm
          before a download starts.
        </p>
      </header>
      <dl className="help-glossary">
        {terms.map((row) => (
          <div key={row.term} className="help-glossary-row">
            <dt>{row.term}</dt>
            <dd>{row.meaning}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
