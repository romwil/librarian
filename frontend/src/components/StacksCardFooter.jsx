/** One visible line. Objects and odd types stay blank so a bad payload cannot invent a caption. */
export function stacksCardLine(value) {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value !== "string") return "";
  return value
    .replace(/[\r\n]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Title and author under a Stacks cover. Missing title becomes Untitled. */
export function stacksCardIdentity(work = {}) {
  const title = stacksCardLine(work?.title) || stacksCardLine(work?.book_title) || "Untitled";
  const author = stacksCardLine(work?.author);
  return { title, author };
}

/** Presentational Stacks footer: title, then author. No shelf status and no Read link. */
export default function StacksCardFooter({ work, tip = "" }) {
  const { title, author } = stacksCardIdentity(work);
  return (
    <div className="stacks-card-footer" data-testid="stacks-card-footer" title={tip || undefined}>
      <span className="stacks-card-title">{title}</span>
      {author ? <span className="stacks-card-author">{author}</span> : null}
    </div>
  );
}
