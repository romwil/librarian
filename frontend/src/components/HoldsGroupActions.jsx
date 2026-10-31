import { useRef, useState } from "react";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  bulkResultHasFailures,
  bulkResultSummary,
  deleteGroupConfirmCopy,
  isDuplicateGroup,
  purgePreviewCopy,
  slipRowIsPathClear,
} from "../review.js";
import ConfirmDialog from "./ConfirmDialog.jsx";

/** One pile's group motions on Sorting: Accept the clear ones, Purge duplicate group, Delete group. */
export default function HoldsGroupActions({ group, onChanged, bulk = api.reviewBulkByReason }) {
  const [busy, setBusy] = useState("");
  const [dialog, setDialog] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [note, setNote] = useState("");
  const [typed, setTyped] = useState("");
  const deleteRef = useRef(null);
  const purgeRef = useRef(null);
  const acceptRef = useRef(null);
  const works = group?.works || [];
  const count = works.length;
  const workIds = works.map((work) => work.id);
  const reason = group?.reason || "";
  const showAccept = works.some((row) => slipRowIsPathClear(row));
  const showPurge = isDuplicateGroup(reason);
  const label = group?.label || "";

  async function run(action, { dryRun = false, confirmCount = null } = {}) {
    setBusy(action);
    setNote("");
    try {
      const data = await bulk({ reason, action, workIds, dryRun, confirmCount });
      if (dryRun) {
        setPreview(data);
        return data;
      }
      setResult(data);
      onChanged?.(data ? { ...data, reason } : data);
      return data;
    } catch (err) {
      setResult(null);
      setNote(humanError(err));
      return null;
    } finally {
      setBusy("");
    }
  }

  async function openPurge() {
    const data = await run("purge_duplicates", { dryRun: true });
    if (data) setDialog("purge");
  }

  async function openAccept() {
    const data = await run("accept_clear", { dryRun: true });
    if (data) {
      setTyped("");
      setDialog("accept");
    }
  }

  async function openDelete() {
    const data = await run("delete", { dryRun: true });
    if (data) {
      setTyped("");
      setDialog("delete");
    }
  }

  async function confirm() {
    const action = dialog === "delete" ? "delete" : dialog === "accept" ? "accept_clear" : "purge_duplicates";
    const needsCount = Boolean(preview?.requires_typed_count);
    const expected = String(Number(preview?.would_change ?? count) || 0);
    if (needsCount && typed.trim() !== expected) return;
    const confirmCount = needsCount ? Number(expected) : null;
    setDialog(null);
    await run(action, { confirmCount });
  }

  const deleteCopy = deleteGroupConfirmCopy({ count, label });
  const purgeCopy = preview ? purgePreviewCopy(preview) : null;
  const summary = result ? bulkResultSummary(result) : note;
  const failed = note || (result && bulkResultHasFailures(result));

  return (
    <>
      <div className="cta-row compact" role="group" aria-label={`${label || "Pile"} group actions`}>
        {showAccept ? (
          <button
            type="button"
            className="cta compact"
            data-testid="accept-clear-ones"
            disabled={Boolean(busy)}
            ref={acceptRef}
            onClick={() => openAccept()}
          >
            {busy === "accept_clear" ? "Filing…" : "Accept the clear ones"}
          </button>
        ) : null}
        {showPurge ? (
          <button
            ref={purgeRef}
            type="button"
            className="cta outline compact"
            disabled={Boolean(busy) || !count}
            onClick={() => openPurge()}
          >
            {busy === "purge_duplicates" ? "Checking…" : "Purge duplicate group"}
          </button>
        ) : null}
        <button
          ref={deleteRef}
          type="button"
          className="cta outline compact"
          disabled={Boolean(busy) || !count}
          onClick={() => openDelete()}
        >
          {busy === "delete" ? "Deleting…" : `Delete group (${count})`}
        </button>
      </div>
      {showPurge && purgeCopy ? (
        <p className="muted holds-group-hint" data-testid="holds-group-evidence">
          Evidence: {purgeCopy.exact} exact fingerprint · {purgeCopy.unassessable} unassessable
          {purgeCopy.others ? ` · ${purgeCopy.others} different files` : ""}
        </p>
      ) : null}
      {summary ? (
        <p className={failed ? "alert" : "muted"} role="status" data-testid="holds-group-result">
          {summary}
        </p>
      ) : null}
      <ConfirmDialog
        open={dialog === "delete"}
        title={deleteCopy.title}
        confirmLabel={deleteCopy.confirmLabel}
        onConfirm={confirm}
        onCancel={() => setDialog(null)}
        busy={busy === "delete"}
        confirmDisabled={Boolean(preview?.requires_typed_count) && typed.trim() !== String(Number(preview?.would_change ?? count) || 0)}
        returnFocusRef={deleteRef}
        testId="delete-group-dialog"
      >
        <p>{deleteCopy.body}</p>
        <p>This pile has {preview?.would_change ?? count} slips.</p>
        {preview?.requires_typed_count ? (
          <label className="field">
            Type {preview.would_change} to confirm
            <input value={typed} onChange={(event) => setTyped(event.target.value)} />
          </label>
        ) : null}
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog === "accept"}
        title={`File ${preview?.would_change ?? count} clear ${label || "slips"}?`}
        confirmLabel="File them"
        onConfirm={confirm}
        onCancel={() => setDialog(null)}
        busy={busy === "accept_clear"}
        confirmDisabled={Boolean(preview?.requires_typed_count) && typed.trim() !== String(Number(preview?.would_change ?? count) || 0)}
        returnFocusRef={acceptRef}
        testId="accept-group-dialog"
      >
        <p>
          {preview?.would_change ?? count} slips in {label || "this pile"} look path-clear and will be filed. Folders stay on disk.
        </p>
        {preview?.requires_typed_count ? (
          <label className="field">
            Type {preview.would_change} to confirm
            <input value={typed} onChange={(event) => setTyped(event.target.value)} />
          </label>
        ) : null}
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog === "purge" && Boolean(purgeCopy)}
        title={purgeCopy?.title || ""}
        confirmLabel={purgeCopy?.confirmLabel || ""}
        onConfirm={purgeCopy?.exact ? confirm : null}
        onCancel={() => setDialog(null)}
        busy={busy === "purge_duplicates"}
        returnFocusRef={purgeRef}
        testId="purge-group-dialog"
      >
        <ul>
          {(purgeCopy?.lines || []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>Download folders stay on disk.</p>
      </ConfirmDialog>
    </>
  );
}
