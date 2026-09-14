import { clothFor, coverCaption, isSquareKind, jobChipLabel, shouldOpenPeek } from "../cover.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

export default function CoverCard({ work, href, onRequest, badge, beyond = false, role = "reader" }) {
  const peek = useWorkPeek();
  const kind = work.kind || "book";
  const square = isSquareKind(kind);
  const title = work.title || "Untitled";
  const status = work.job_status || badge;
  const chip = status ? jobChipLabel(status, role) : "";

  function onClick(event) {
    if (!shouldOpenPeek(event)) return;
    event.preventDefault();
    peek.openWork({ ...work, beyond, job_status: status }, { triggerEl: event.currentTarget, onRequest });
  }

  const classes = ["cover"];
  if (square) classes.push("is-square");
  if (work.progress) classes.push("is-progress");
  if (work.gap || kind === "gap") classes.push("is-gap");

  return (
    <div className="cover-unit">
      <button
        type="button"
        className={classes.join(" ")}
        style={{ "--cloth": work.cloth || clothFor(title), "--progress": `${work.progress || 0}%` }}
        onClick={onClick}
      >
        <strong>{title}</strong>
        <em>{work.author || work.series_name || kind}</em>
        {chip ? <span className={`live-chip${status === "asked" ? " is-asked" : ""}${status === "failed" ? " is-failed" : ""}`}>{chip}</span> : null}
      </button>
      <p className="cover-caption">{coverCaption(work)}</p>
    </div>
  );
}
