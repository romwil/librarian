import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clothFor,
  coverCaption,
  coverClassNames,
  coverDisplayTitle,
  coverOverlay,
  coverShapeClass,
  coverTip,
  formatPubAge,
  formatSize,
  humanizeReleaseTitle,
  isBeyondWork,
  isLandscapeKind,
  isSquareKind,
  isInboundJob,
  jobChipLabel,
  jobHouseholdLabel,
  jobNeedsYouReason,
  jobQueueDetail,
  partHint,
  shouldOpenPeek,
} from "./cover.js";

describe("reading room cover helpers", () => {
  it("picks a stable cloth color from the title", () => {
    assert.equal(clothFor("Piranesi"), clothFor("Piranesi"));
    assert.notEqual(clothFor("Piranesi"), clothFor("Circe"));
  });

  it("opens peek on a plain click and not a modifier click", () => {
    assert.equal(shouldOpenPeek({ metaKey: false, ctrlKey: false, shiftKey: false, altKey: false }), true);
    assert.equal(shouldOpenPeek({ metaKey: true, ctrlKey: false, shiftKey: false, altKey: false }), false);
  });

  it("skins kinds with different shapes", () => {
    assert.equal(isSquareKind("music"), true);
    assert.equal(isSquareKind("audiobook"), false);
    assert.equal(isLandscapeKind("audiobook"), true);
    assert.equal(isSquareKind("book"), false);
    assert.equal(isSquareKind("comic"), false);
    assert.equal(coverShapeClass("book"), "is-portrait");
    assert.equal(coverShapeClass("magazine"), "is-magazine");
    assert.equal(coverShapeClass("comic"), "is-comic");
    assert.equal(coverShapeClass("audiobook"), "is-landscape");
    assert.equal(coverShapeClass("music"), "is-square");
    assert.match(coverClassNames({ kind: "book", title: "Dune" }), /cover-book is-portrait/);
    assert.match(coverClassNames({ kind: "music", music_state: "incoming" }), /is-incoming/);
  });

  it("collapses living request chips to household words", () => {
    assert.equal(jobChipLabel(undefined, "reader"), "Ask the house");
    assert.equal(jobChipLabel(undefined, "owner"), "Request");
    assert.equal(jobChipLabel("asked"), "Asked");
    assert.equal(jobHouseholdLabel("queued"), "On the way");
    assert.equal(jobChipLabel("downloading"), "On the way");
    assert.equal(jobChipLabel("extracting"), "On the way");
    assert.equal(jobChipLabel("identifying"), "On the way");
    assert.equal(isInboundJob("extracting"), true);
    assert.equal(jobChipLabel("organized"), "Arrived");
    assert.equal(jobChipLabel("review"), "Needs you");
    assert.equal(jobChipLabel("failed"), "Failed");
  });

  it("keeps SAB raw on Queue detail only", () => {
    assert.equal(jobQueueDetail({ sab_status: "Verifying", nzo_id: "nzo_abc" }), "Verifying · nzo_abc");
    assert.equal(jobQueueDetail({ status: "extracting", nzo_id: "nzo_abc" }), "Extracting · nzo_abc");
    assert.equal(jobQueueDetail({ status: "asked" }), "Asked slip");
    assert.equal(
      jobQueueDetail({
        status: "failed",
        error: "Unpack did not finish; archives remain in the complete folder",
        nzo_id: "SABnzbd_nzo_mix",
      }),
      "Unpack did not finish; archives remain in the complete folder · SABnzbd_nzo_mix",
    );
    assert.equal(
      jobQueueDetail({
        status: "identifying",
        payload: { source: "ingest" },
        storage_path: "/data/inbox/Book.epub",
      }),
      "/data/inbox/Book.epub",
    );
  });

  it("keeps Needs you ops detail muted and explains the review reason separately", () => {
    assert.equal(
      jobQueueDetail({
        status: "review",
        nzo_id: "3ed43dc9-188e-48db-91ba-487a96bc7084",
        review_reason: "unknown_identity",
      }),
      "3ed43dc9-188e-48db-91ba-487a96bc7084",
    );
    assert.match(
      jobNeedsYouReason({
        status: "review",
        review_reason: "unknown_identity",
        nzo_id: "3ed43dc9-188e-48db-91ba-487a96bc7084",
      }),
      /Identity unclear/,
    );
    assert.match(
      jobNeedsYouReason({
        status: "review",
        error: "Radarr is not configured",
        review_reason: "unknown_identity",
      }),
      /Radarr is not configured/,
    );
    assert.equal(jobNeedsYouReason({ status: "failed", error: "boom" }), "");
  });

  it("uses issue dates and numbers as gilt captions", () => {
    assert.equal(coverCaption({ kind: "magazine", series_index: "2026-09", title: "The Atlantic" }), "2026-09");
    assert.equal(coverCaption({ kind: "comic", series_name: "Saga", series_index: "54" }), "Saga #54");
    assert.equal(coverCaption({ kind: "book", title: "Piranesi" }), "Piranesi");
    assert.equal(coverCaption({ kind: "music", title: "Dummy", music_state: "incoming" }), "Dummy · incoming");
  });

  it("puts magazine masthead and comic numbers in the overlay, not a book spine", () => {
    assert.equal(coverOverlay({ kind: "magazine", title: "The Atlantic", series_index: "2026-09" }).chip, "2026-09");
    assert.equal(coverOverlay({ kind: "comic", series_name: "Saga", series_index: "54", title: "Saga" }).chip, "#54");
    assert.equal(coverOverlay({ kind: "audiobook", title: "Dune", duration: "21h" }).chip, "21h");
    assert.equal(coverOverlay({ kind: "music", title: "Dummy", music_state: "incoming" }).chip, "Incoming");
    assert.equal(coverOverlay({ kind: "book", title: "Piranesi", author: "Clarke" }).byline, "Clarke");
  });

  it("humanizes dotted Usenet dumps without inventing shelf titles", () => {
    assert.equal(
      humanizeReleaseTitle("Dynamite.-.Aladdin.No.03.2026.Hybrid.Comic.eBook-BitBook"),
      "Dynamite - Aladdin No 03 2026",
    );
    assert.equal(humanizeReleaseTitle("Piranesi"), "Piranesi");
    assert.equal(formatSize(461602113), "440 MB");
    assert.equal(formatSize(0), "");
    assert.equal(partHint("Title [03/12]"), "3/12");
    assert.equal(partHint("Title CD2"), "p2");
    assert.match(formatPubAge(new Date(Date.now() - 3 * 60 * 60 * 1000).toUTCString()), /3h/);
  });

  it("puts size and age on beyond cover faces instead of Library", () => {
    const hit = {
      beyond: true,
      kind: "comic",
      title: "Dynamite.-.Aladdin.No.03.2026.Hybrid.Comic.eBook-BitBook",
      size: 50 * 1024 * 1024,
      pub_date: new Date(Date.now() - 2 * 60 * 60 * 1000).toUTCString(),
      host_name: "NZBFinder",
      guid: "g1",
    };
    assert.equal(isBeyondWork(hit), true);
    assert.equal(coverDisplayTitle(hit), "Dynamite - Aladdin No 03 2026");
    const face = coverOverlay(hit);
    assert.equal(face.title, "Dynamite - Aladdin No 03 2026");
    assert.match(face.byline, /comic/);
    assert.match(face.byline, /50 MB/);
    assert.match(face.byline, /2h/);
    assert.equal(coverOverlay({ ...hit, kind: "music" }).chip, "");
    assert.match(coverCaption(hit), /50 MB/);
    assert.match(coverTip(hit), /NZBFinder/);
  });
  it("labels movie/tv/xxx beyond covers in the byline, not Book", () => {
    const movie = coverOverlay({
      beyond: true,
      kind: "movie",
      title: "Solo.A.Star.Wars.Story.(2018).VFF.2160p",
      size: 5000000000,
      pub_date: new Date(Date.now() - 2 * 60 * 60 * 1000).toUTCString(),
      guid: "g-movie",
    });
    assert.match(movie.byline, /^movie\b/);
    assert.match(movie.byline, /GB|MB|KB/);
    assert.equal(movie.chip, "");
    assert.match(coverOverlay({ beyond: true, kind: "tv", title: "Show.S01E01", guid: "g-tv" }).byline, /^tv\b/);
    assert.match(coverOverlay({ beyond: true, kind: "xxx", title: "Clip", guid: "g-xxx" }).byline, /^xxx\b/);
    assert.match(
      coverOverlay({ beyond: true, kind: "book", title: "Piranesi", guid: "g-book" }).byline,
      /Book|MB|KB|h|d|m/,
    );
  });

});
