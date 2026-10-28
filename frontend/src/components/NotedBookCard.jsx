import { clothFor } from "../cover.js";

/** One noted title: cloth spine, Literata title, a short status, then that book's actions. */
export default function NotedBookCard({ book, status = "", weeks = "", testId = "noted-book", children }) {
  const title = String(book?.title || "").trim();
  const author = String(book?.author || "").trim();
  return (
    <li className="noted-book" data-testid={testId} data-status={status ? status.toLowerCase() : undefined}>
      <span
        className="noted-book-spine"
        style={{ "--cloth": clothFor(title || author) }}
        aria-hidden="true"
      />
      <div className="noted-book-copy">
        <h3 className="noted-book-title">{title}</h3>
        {author ? <p className="noted-book-author">{author}</p> : null}
        {weeks || status ? (
          <p className="noted-book-meta">
            {weeks ? <span className="noted-book-weeks">{weeks}</span> : null}
            {status ? <span className="noted-book-status">{status}</span> : null}
          </p>
        ) : null}
      </div>
      {children ? <div className="noted-book-actions cta-row">{children}</div> : null}
    </li>
  );
}
