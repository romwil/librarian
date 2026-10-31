"""Docs stay honest with the Hall and Sorting names."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_help_drops_radarr_sonarr_xxx():
    text = (ROOT / "docs" / "HELP.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "radarr" not in lower
    assert "sonarr" not in lower
    assert "xxx" not in lower
    assert "Sorting" in text
    assert "The Hall" in text


def test_north_star_names_hall_and_sorting():
    path = ROOT / "docs" / "superpowers" / "specs" / "2026-11-librarian-north-star.md"
    text = path.read_text(encoding="utf-8")
    assert "The Hall is the living front" in text
    assert "Sorting" in text
    assert "There is no Place a hold" in text
    assert "product control" in text
    assert "0.6" in text or "8793" in text
