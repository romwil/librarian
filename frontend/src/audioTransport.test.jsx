// @vitest-environment jsdom
import assert from "node:assert/strict";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, it } from "vitest";
import AudiobookPlayer from "./components/AudiobookPlayer.jsx";
import { useAlbumPlayer } from "./hooks/useAlbumPlayer.js";
import { useAudioTransport } from "./hooks/useAudioTransport.js";

const media = HTMLMediaElement.prototype;
const real = { play: media.play, pause: media.pause, load: media.load };
const realFetch = globalThis.fetch;
let rejectPlay = false;
let posts = [];

function fire(audio, type) {
  act(() => {
    audio.dispatchEvent(new Event(type));
  });
}

beforeEach(() => {
  rejectPlay = false;
  posts = [];
  Object.defineProperty(media, "paused", {
    configurable: true,
    get() {
      return this._paused !== false;
    },
  });
  media.play = function play() {
    if (rejectPlay) return Promise.reject(new Error("NotAllowedError"));
    this._paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  };
  media.pause = function pause() {
    if (this._paused === false) {
      this._paused = true;
      this.dispatchEvent(new Event("pause"));
    }
  };
  media.load = function load() {};
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    if (init.method === "POST") posts.push({ path, body: JSON.parse(init.body || "{}") });
    const body = path.includes("/chapters") ? { chapters: [] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  };
});

afterEach(() => {
  Object.assign(media, real);
  delete media.paused;
  globalThis.fetch = realFetch;
});

describe("useAudioTransport", () => {
  function Harness({ onEvent }) {
    const [shown, setShown] = useState(false);
    const [count, setCount] = useState(0);
    const transport = useAudioTransport({
      onPlay: () => onEvent(`play:${count}`),
      onEnded: () => onEvent(`ended:${count}`),
      onPlayRejected: () => onEvent("rejected"),
    });
    return (
      <div>
        <button type="button" onClick={() => setShown(true)}>
          Mount
        </button>
        <button type="button" onClick={() => setCount((n) => n + 1)}>
          Bump
        </button>
        <button type="button" onClick={() => transport.start("/api/works/w/stream?file=1")}>
          Start
        </button>
        <button type="button" onClick={() => transport.silence()}>
          Silence
        </button>
        {shown ? <audio ref={transport.audioRef} data-testid="audio" /> : null}
      </div>
    );
  }

  it("binds to an <audio> that mounts late and reads fresh handlers", async () => {
    const seen = [];
    render(<Harness onEvent={(name) => seen.push(name)} />);
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    assert.deepEqual(seen, [], "no element yet, nothing to play");

    await userEvent.click(screen.getByRole("button", { name: "Mount" }));
    await userEvent.click(screen.getByRole("button", { name: "Bump" }));
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    const audio = screen.getByTestId("audio");
    assert.match(audio.getAttribute("src"), /stream\?file=1$/);
    fire(audio, "ended");
    assert.deepEqual(seen, ["play:1", "ended:1"]);

    await userEvent.click(screen.getByRole("button", { name: "Silence" }));
    assert.equal(audio.hasAttribute("src"), false);
    assert.equal(audio.paused, true);
  });

  it("reports a refused play() instead of leaving a stuck Pause", async () => {
    const seen = [];
    render(<Harness onEvent={(name) => seen.push(name)} />);
    await userEvent.click(screen.getByRole("button", { name: "Mount" }));
    rejectPlay = true;
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => assert.deepEqual(seen, ["rejected"]));
  });
});

const ALBUM = [
  { id: "t1", filename: "01 Opening.flac" },
  { id: "t2", filename: "02 Middle.flac" },
  { id: "cover", filename: "cover.jpg" },
];

function AlbumHarness() {
  const album = useAlbumPlayer({ workId: "album-1", files: ALBUM, enabled: true });
  return (
    <div>
      <button type="button" onClick={album.toggleAlbum}>
        {album.active ? "Stop" : "Play"}
      </button>
      <p data-testid="now">{album.nowPlayingLabel}</p>
      <audio ref={album.audioRef} data-testid="album-audio" />
    </div>
  );
}

describe("album player on the shared transport", () => {
  it("plays the album in order, then stops after the last track", async () => {
    render(<AlbumHarness />);
    const audio = screen.getByTestId("album-audio");
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    assert.equal(screen.getByTestId("now").textContent, "01 Opening.flac");
    assert.match(audio.getAttribute("src"), /file=t1$/);

    fire(audio, "ended");
    assert.equal(screen.getByTestId("now").textContent, "02 Middle.flac");
    assert.match(audio.getAttribute("src"), /file=t2$/);

    fire(audio, "ended");
    assert.equal(screen.getByTestId("now").textContent, "");
    assert.equal(audio.hasAttribute("src"), false);
    assert.ok(screen.getByRole("button", { name: "Play" }));
  });

  it("drops back to Play when the browser refuses to start", async () => {
    render(<AlbumHarness />);
    rejectPlay = true;
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    await waitFor(() => assert.ok(screen.getByRole("button", { name: "Play" })));
    assert.equal(screen.getByTestId("now").textContent, "");
  });
});

describe("Listening room on the shared transport", () => {
  const work = { id: "ab-1", title: "Long Listen", author: "N. Arrator", kind: "audiobook" };
  const files = [
    { id: "p1", filename: "Part 1.m4b" },
    { id: "p2", filename: "Part 2.m4b" },
  ];

  it("plays when the part is ready, follows Pause, and finishes after the last part", async () => {
    render(<AudiobookPlayer work={work} files={files} onClose={() => {}} />);
    const audio = screen.getByTestId("listen-audio");
    assert.match(audio.getAttribute("src"), /file=p1$/);
    assert.ok(screen.getByText("Opening the volume…"));

    fire(audio, "loadedmetadata");
    const toggle = screen.getByRole("button", { name: "Pause" });
    assert.equal(screen.queryByText("Opening the volume…"), null);

    await userEvent.click(toggle);
    assert.ok(screen.getByRole("button", { name: "Play" }));

    fire(audio, "ended");
    assert.match(audio.getAttribute("src"), /file=p2$/);
    fire(audio, "loadedmetadata");
    fire(audio, "ended");
    await waitFor(() =>
      assert.ok(posts.some((row) => row.path.endsWith("/works/ab-1/progress") && row.body.finished === true)),
    );
  });

  it("says so when a part cannot be streamed", () => {
    render(<AudiobookPlayer work={work} files={files} onClose={() => {}} />);
    fire(screen.getByTestId("listen-audio"), "error");
    assert.match(screen.getByText(/could not be streamed/i).textContent, /could not be streamed/i);
    assert.ok(screen.getByRole("button", { name: "Play" }));
  });
});
