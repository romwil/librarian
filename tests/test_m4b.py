"""M4B remux helpers — ffmpeg mocked via injectable runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from librarian.m4b import (
    build_m4b,
    chapters_from_audnexus,
    chapters_from_boundaries,
    needs_m4b_remux,
    validate_m4b,
)


def test_needs_m4b_remux(tmp_path):
    single = tmp_path / "book.m4b"
    single.write_bytes(b"x" * 100)
    assert needs_m4b_remux([single]) is False
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    assert needs_m4b_remux([a, b]) is True
    flac = tmp_path / "book.flac"
    flac.write_bytes(b"f")
    assert needs_m4b_remux([flac]) is True


def test_chapters_from_audnexus_ms_offsets():
    rows = chapters_from_audnexus(
        [
            {"title": "Opening", "startOffsetMs": 0},
            {"title": "Chapter 2", "startOffsetMs": 120000},
        ]
    )
    assert rows[0]["start"] == 0.0
    assert rows[1]["start"] == 120.0
    assert rows[1]["title"] == "Chapter 2"


def test_build_m4b_with_fake_ffmpeg(tmp_path):
    src_a = tmp_path / "01.mp3"
    src_b = tmp_path / "02.mp3"
    src_a.write_bytes(b"aaa")
    src_b.write_bytes(b"bbb")
    dest = tmp_path / "out" / "Book.m4b"

    def fake_runner(argv, *, timeout=120, cwd=None):
        # ffprobe duration
        if argv and "ffprobe" in str(argv[0]):
            return subprocess.CompletedProcess(argv, 0, stdout=b"10.0\n", stderr=b"")
        # ffmpeg write staging output
        if argv and "ffmpeg" in str(argv[0]):
            out = Path(argv[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"m4b-bytes" * 20)
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"unknown")

    # Pretend tools exist
    import librarian.m4b as m4b_mod

    original_ffmpeg = m4b_mod.which_ffmpeg
    original_ffprobe = m4b_mod.which_ffprobe
    m4b_mod.which_ffmpeg = lambda: "/usr/bin/ffmpeg"
    m4b_mod.which_ffprobe = lambda: "/usr/bin/ffprobe"
    try:
        chapters = chapters_from_boundaries([src_a, src_b], runner=fake_runner)
        assert len(chapters) == 2
        built = build_m4b(
            [src_a, src_b],
            dest,
            chapters=chapters,
            tags={"title": "Book", "author": "Author", "asin": "B08G9PRS1K"},
            runner=fake_runner,
            work_dir=tmp_path / "work",
        )
        assert built == dest
        assert dest.is_file()
        assert validate_m4b(dest, runner=fake_runner)
    finally:
        m4b_mod.which_ffmpeg = original_ffmpeg
        m4b_mod.which_ffprobe = original_ffprobe
