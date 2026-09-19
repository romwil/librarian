import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  chaseCandidateRows,
  chaseConversationLines,
  chaseResultRows,
  chaseStepLines,
  chaseTraceSummary,
} from "./chaseTrace.js";

describe("chaseTrace helpers", () => {
  const chase = {
    book_hit: null,
    audiobook_hit: null,
    trace: {
      conversation: [
        { role: "user", content: "Find ebook and audiobook for 'The Art of War' by 'Sun Tzu'" },
        { role: "assistant", content: "Book plan: books; raw=2 accepted_pick=none" },
      ],
      book: {
        raw_count: 2,
        rejected_count: 2,
        error: null,
        steps: [{ step: "plan", detail: "books title='The Art of War'" }],
        results: [
          {
            decision: "rejected",
            reason: "kind None not shelfable",
            title: "Sun Tzu - The Art of War",
            guid: "art-1",
            kind: "",
            host_name: "NZBFinder",
            notes: [],
          },
          {
            decision: "skipped",
            reason: "missing guid (shown but not requestable)",
            title: "Art of War ebook",
            guid: "",
            kind: "book",
            host_name: "NZBFinder",
            notes: ["assumed kind=book (missing category)"],
          },
        ],
      },
      audiobook: {
        raw_count: 0,
        rejected_count: 0,
        error: "NZBFinder api_token is not configured",
        steps: [],
        results: [],
      },
    },
  };

  it("summarizes filtered ebook hits and audiobook errors", () => {
    const summary = chaseTraceSummary(chase);
    assert.match(summary, /ebook raw 2/);
    assert.match(summary, /audiobook raw 0/);
    assert.match(summary, /ebook hits filtered/);
    assert.match(summary, /NZBFinder api_token/);
  });

  it("exposes conversation and result rows for the disclosure", () => {
    assert.equal(chaseConversationLines(chase).length, 2);
    const rows = chaseResultRows(chase);
    assert.equal(rows.length, 2);
    assert.equal(rows[0].decision, "rejected");
    assert.match(rows[0].reason, /not shelfable/);
    assert.equal(rows[1].decision, "skipped");
    assert.equal(chaseStepLines(chase)[0].detail.includes("Art of War"), true);
  });
});

describe("chaseCandidateRows", () => {
  it("lists remembered alternates per lane", () => {
    const rows = chaseCandidateRows({
      book_candidates: [{ guid: "b1", title: "Ebook", rank: 1, note: "heuristic" }],
      trace: {
        audiobook: {
          candidates: [{ guid: "a1", title: "Audio", rank: 2 }],
          rank_method: "llm",
        },
      },
    });
    assert.equal(rows.length, 2);
    assert.equal(rows[0].guid, "b1");
    assert.equal(rows[1].guid, "a1");
    assert.equal(rows[1].method, "llm");
  });
});

