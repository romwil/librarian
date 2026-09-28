"""Gaps as gifts + search that forgives."""

from librarian.gaps_gifts import frame_gap_as_gift, gift_invitation, gift_presence
from librarian.search_forgive import did_you_mean, forgive_fts_query, search_with_forgiveness


def test_gift_invitation_voice():
    card = frame_gap_as_gift(
        {"series_name": "Saga", "series_index": "4", "kind": "comic", "title": "Saga 4"}
    )
    assert card["gift"] is True
    assert "complete the run" in card["invitation"].lower() or "Saga" in card["invitation"]
    assert "admin" not in gift_invitation(card).lower()
    assert "whole" in gift_presence([]).lower()


def test_forgive_prefix_and_did_you_mean():
    assert '"dune"*' in forgive_fts_query("dune")
    assert did_you_mean(["Dune", "Foundation", "Neuromancer"], "Dun") == ["Dune"]


class _FakeDb:
    def __init__(self):
        self.calls = []

    def search_works(self, q, *, limit=24, kind=None):
        self.calls.append(("exact", q))
        return []

    def search_works_raw(self, match, *, limit=24, kind=None):
        self.calls.append(("raw", match))
        if "dun" in match.lower():
            return [{"id": "1", "title": "Dune"}]
        return []

    def suggest_values(self, *, field, kind="", q="", limit=12):
        return ["Dune", "Foundation"]


def test_search_with_forgiveness_falls_back():
    result = search_with_forgiveness(_FakeDb(), "dun", limit=8)
    assert result["forgave"] is True
    assert result["local"][0]["title"] == "Dune"
