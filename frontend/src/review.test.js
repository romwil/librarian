import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyBodyFromDraft,
  collisionActionCopy,
  collisionApplyAllowed,
  collisionDraftUnchanged,
  effectiveReviewReason,
  fieldsFromWork,
  queueReviewReasonCopy,
  reviewActionsFromWork,
  reviewDiagnosisCopy,
  reviewFindHref,
  reviewReasonCopy,
  unpackStuckWorks,
} from "./review.js";

describe("review identify form", () => {
  it("explains no_payload without blaming SAB path mapping first", () => {
    const copy = reviewReasonCopy("no_payload");
    assert.match(copy, /cannot invent/);
    assert.doesNotMatch(copy, /complete root to map/);
  });

  it("explains unpack_stuck as leftover archives", () => {
    const copy = reviewReasonCopy("unpack_stuck");
    assert.match(copy, /archives/i);
    assert.match(copy, /unpack/i);
  });

  it("builds a diagnosis block for Guardians-style unpack stuck", () => {
    const work = {
      review_reason: "no_payload",
      folder_diagnosis: {
        problem: "unpack_stuck",
        archive_count: 3,
        junk_count: 2,
        tried: "Opened /data/usenet/complete/downloads/VA-Guardians. Found 3 archive file(s).",
        looked_for: "book (epub/pdf), comic (cbz/cbr), or audio (flac/mp3/m4a/m4b) files",
        path_note: "The …/complete/downloads/… path is normal",
        suggested_folder: null,
      },
    };
    assert.equal(effectiveReviewReason(work), "unpack_stuck");
    const diagnosis = reviewDiagnosisCopy(work);
    assert.match(diagnosis.meaning, /could not finish/i);
    assert.match(diagnosis.tried, /Opened/);
    assert.match(diagnosis.whatsWrong, /Archives remain/i);
    assert.match(diagnosis.nextSteps, /unar|SABnzbd|Skip/i);
    assert.match(diagnosis.pathNote, /complete\/downloads/);
  });

  it("explains collision Skip vs Apply without overwrite", () => {
    const copy = reviewReasonCopy("collision");
    assert.match(copy, /[Cc]ollision/);
    assert.match(copy, /will not silent-overwrite|will not overwrite/i);
    assert.match(collisionActionCopy(), /Skip keeps/);
    assert.match(collisionActionCopy(), /will not overwrite/i);
  });

  it("blocks Apply on collision until identity or folder changes", () => {
    const work = {
      title: "To the Edge",
      author: "Cindy Gerard",
      kind: "book",
      isbn: "9780312990916",
      series_name: "Bodyguards",
      series_index: "1",
      folder_path: "/data/media/books/Cindy Gerard/To the Edge (1216)",
    };
    const draft = fieldsFromWork(work);
    assert.equal(collisionDraftUnchanged(draft, work), true);
    assert.equal(collisionApplyAllowed("collision", draft, work), false);
    assert.equal(collisionApplyAllowed("collision", { ...draft, title: "To the Edge (alt)" }, work), true);
    assert.equal(collisionApplyAllowed("unknown_identity", draft, work), true);
  });

  it("shortens review reasons for Queue Needs you cards", () => {
    assert.match(queueReviewReasonCopy("extra_files"), /Extra files/);
    assert.match(queueReviewReasonCopy("collision"), /Open Review/i);
    assert.match(queueReviewReasonCopy("collision"), /shelf/i);
    assert.match(queueReviewReasonCopy("unpack_stuck"), /Archives/);
    assert.match(queueReviewReasonCopy(""), /Waiting in Review/);
  });

  it("prefills folder from SAB storage when work.folder_path is empty", () => {
    const fields = fieldsFromWork({
      title: "Christine",
      author: "Stephen King",
      kind: "book",
      folder_path: null,
      storage_path: "/downloads/books/Christine - Stephen King/Christine - Stephen King.epub",
    });
    assert.equal(fields.title, "Christine");
    assert.match(fields.folder, /Christine - Stephen King\.epub$/);
  });

  it("posts identity fields including folder", () => {
    const body = applyBodyFromDraft({
      title: "The Return of the King",
      author: "J. R. R. Tolkien",
      kind: "audiobook",
      isbn: "",
      series_name: "",
      series_index: "",
      year: "1955",
      folder: "/data/complete/Return",
    });
    assert.equal(body.kind, "audiobook");
    assert.equal(body.year, 1955);
    assert.equal(body.folder, "/data/complete/Return");
  });
});

describe("review recovery actions", () => {
  it("reads actions flags and builds /find?q=&kind= deep-link", () => {
    const work = {
      title: "Guardians Mix",
      author: "Various",
      kind: "music",
      review_reason: "unpack_stuck",
      actions: { can_repair: true, can_retry: true, find_query: "Guardians Mix" },
    };
    const actions = reviewActionsFromWork(work);
    assert.equal(actions.canRepair, true);
    assert.equal(actions.canRetry, true);
    assert.equal(reviewFindHref(work), "/find?q=Guardians+Mix&kind=music");
  });

  it("filters unpack_stuck slips for bulk Repair/Retry", () => {
    const works = [
      { id: "a", review_reason: "unpack_stuck", folder_diagnosis: { problem: "unpack_stuck" } },
      { id: "b", review_reason: "collision" },
      { id: "c", review_reason: "no_payload", folder_diagnosis: { problem: "unpack_stuck" } },
    ];
    assert.deepEqual(
      unpackStuckWorks(works).map((row) => row.id),
      ["a", "c"],
    );
  });
});
