import { Link } from "react-router-dom";
import { browseHref } from "../browse.js";

const COLUMN_LABELS = {
  title: "Title",
  author: "Author",
  year: "Year",
  kind: "Kind",
  series: "Series",
  genre: "Genre",
};

function cellValue(work, column) {
  if (column === "series") return work.series_name || "";
  return work[column] == null ? "" : String(work[column]);
}

/** Stacks List view — same filtered rows as the cover grid, one row per work. */
export default function BrowseListView({ items, columns }) {
  const cols = columns.length ? columns : ["title"];
  return (
    <div className="stacks-list" data-testid="stacks-list">
      <div className="stacks-list-row stacks-list-header" aria-hidden="true">
        {cols.map((col) => (
          <span key={col}>{COLUMN_LABELS[col] || col}</span>
        ))}
      </div>
      {items.map((work) => (
        <div className="stacks-list-row" key={work.id} data-testid="stacks-list-row">
          {cols.map((col) =>
            col === "title" ? (
              <span key={col} className="stacks-list-title">
                <Link to={`/works/${encodeURIComponent(work.id)}`}>{work.title || "Untitled"}</Link>
              </span>
            ) : col === "author" && work.author ? (
              <span key={col}>
                <Link to={browseHref({ author: work.author })}>{work.author}</Link>
              </span>
            ) : (
              <span key={col}>{cellValue(work, col)}</span>
            ),
          )}
        </div>
      ))}
    </div>
  );
}
