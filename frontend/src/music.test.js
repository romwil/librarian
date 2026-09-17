import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isAudioFile,
  nextTrackAfter,
  playableTracks,
  playerAfterEnded,
  playerToggleAlbum,
  playerToggleTrack,
  workStreamUrl,
} from "./music.js";

describe("album playback helpers", () => {
  const tracks = [
    { id: "a", filename: "01-intro.flac" },
    { id: "b", filename: "02-song.mp3" },
    { id: "c", filename: "cover.jpg" },
    { id: "d", filename: "03-outro.m4a", on_disk: false },
    { id: "e", filename: "notes.pdf" },
  ];

  it("keeps only on-disk audio extensions (not EPUB/PDF/cover)", () => {
    assert.equal(isAudioFile({ filename: "01.flac" }), true);
    assert.equal(isAudioFile({ filename: "notes.pdf" }), false);
    assert.equal(isAudioFile({ filename: "book.epub" }), false);
    const playable = playableTracks(tracks);
    assert.deepEqual(
      playable.map((row) => row.filename),
      ["01-intro.flac", "02-song.mp3"],
    );
  });

  it("builds a single-file stream URL (never zip)", () => {
    assert.equal(workStreamUrl("w1", "f2"), "/api/works/w1/stream?file=f2");
    assert.equal(workStreamUrl("", "f2"), "");
  });

  it("advances album queue by filename order and clears at the end", () => {
    const playable = playableTracks(tracks);
    assert.equal(nextTrackAfter(playable, "a")?.id, "b");
    assert.equal(nextTrackAfter(playable, "b"), null);
    assert.deepEqual(playerAfterEnded({ playingId: "a", mode: "album" }, playable), {
      playingId: "b",
      mode: "album",
    });
    assert.deepEqual(playerAfterEnded({ playingId: "b", mode: "album" }, playable), {
      playingId: null,
      mode: null,
    });
    assert.deepEqual(playerAfterEnded({ playingId: "a", mode: "single" }, playable), {
      playingId: null,
      mode: null,
    });
  });

  it("toggles per-track Play/Stop and album Play clears when anything is playing", () => {
    const playable = playableTracks(tracks);
    assert.deepEqual(playerToggleTrack({ playingId: null, mode: null }, "a"), {
      playingId: "a",
      mode: "single",
    });
    assert.deepEqual(playerToggleTrack({ playingId: "a", mode: "single" }, "a"), {
      playingId: null,
      mode: null,
    });
    assert.deepEqual(playerToggleAlbum({ playingId: null, mode: null }, playable), {
      playingId: "a",
      mode: "album",
    });
    assert.deepEqual(playerToggleAlbum({ playingId: "b", mode: "single" }, playable), {
      playingId: null,
      mode: null,
    });
  });
});
