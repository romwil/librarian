"""Golden fixtures for audiobook scene normalization."""

from __future__ import annotations

import json
from pathlib import Path

from librarian.audiobook_normalize import normalize_audiobook_name

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "audiobook" / "scene_normalization.json"


def test_scene_normalization_golden_fixtures():
    rows = json.loads(FIXTURES.read_text(encoding="utf-8"))
    assert len(rows) >= 15
    for row in rows:
        tokens = normalize_audiobook_name(row["input"])
        expect = row["expect"]
        for key, wanted in expect.items():
            got = getattr(tokens, key)
            assert got == wanted, f"{row['id']}.{key}: {got!r} != {wanted!r}"
