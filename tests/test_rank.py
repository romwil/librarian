"""Indexer hit ranking — LLM best-match with heuristic degrade."""

from __future__ import annotations

import httpx

from librarian.indexers.rank import (
    heuristic_rank,
    rank_beyond_hits,
    remember_candidates,
    search_and_rank,
)
from librarian.llm import LLMClient, LLMError, reset_llm_rate_limit_state


def _hit(guid: str, title: str, author: str = "Author", kind: str = "book"):
    return {
        "guid": guid,
        "title": title,
        "book_title": title,
        "author": author,
        "kind": kind,
        "host_name": "NZBFinder",
    }


def test_heuristic_rank_prefers_title_author_overlap():
    sought = {"title": "Dune", "author": "Frank Herbert", "kind": "book"}
    hits = [
        _hit("wrong", "Foundation", "Asimov"),
        _hit("right", "Dune", "Frank Herbert"),
        _hit("partial", "Dune Messiah", "Herbert"),
    ]
    ordered = heuristic_rank(hits, sought)
    assert ordered[0]["guid"] == "right"


def test_remember_candidates_requires_guid_and_caps():
    rows = remember_candidates(
        [_hit("a", "A"), {"title": "no guid"}, _hit("a", "dup"), _hit("b", "B")],
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0]["guid"] == "a"
    assert rows[0]["rank"] == 1


def test_rank_beyond_hits_llm_pick(monkeypatch):
    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"guid":"g2","reason":"best","ranked":["g2","g1"]}'
                        }
                    }
                ]
            },
        )

    client = LLMClient("http://llm.example/v1", "k", "m", transport=httpx.MockTransport(handler))
    ranked = rank_beyond_hits(
        [_hit("g1", "Almost Dune", "Herbert"), _hit("g2", "Dune", "Frank Herbert")],
        {"title": "Dune", "author": "Frank Herbert", "kind": "book"},
        llm=client,
    )
    assert ranked["method"] == "llm"
    assert ranked["pick"]["guid"] == "g2"
    assert [row["guid"] for row in ranked["candidates"][:2]] == ["g2", "g1"]
    reset_llm_rate_limit_state()


def test_rank_beyond_hits_degrades_on_429(monkeypatch):
    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "slow"})

    client = LLMClient(
        "http://llm.example/v1",
        "k",
        "m",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    ranked = rank_beyond_hits(
        [_hit("g1", "Dune", "Frank Herbert"), _hit("g2", "Other", "X")],
        {"title": "Dune", "author": "Frank Herbert", "kind": "book"},
        llm=client,
    )
    assert ranked["method"] == "heuristic"
    assert ranked["pick"]["guid"] == "g1"
    assert ranked["candidates"]
    assert "rate-limited" in (ranked["reason"] or "").lower() or "rate-limited" in (ranked["error"] or "").lower()
    reset_llm_rate_limit_state()


def test_search_and_rank_wires_traced_search(monkeypatch):
    def fake_search(settings, *, transport=None, **fields):
        return {
            "hits": [_hit("z", fields.get("title") or "Z", fields.get("author") or "")],
            "error": None,
            "plan": {"endpoint": "books", "params": {}, "sought": fields},
            "steps": [{"step": "plan", "detail": "books"}],
            "raw_count": 1,
            "rejected_count": 0,
            "results": [],
        }

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond_traced", fake_search)
    out = search_and_rank(object(), title="Dune", author="Herbert", kind="book", q="Herbert Dune")
    assert out["pick"]["guid"] == "z"
    assert out["rank_method"] == "heuristic"
    assert out["candidates"][0]["guid"] == "z"
    assert any(step.get("step") == "rank" for step in out["steps"])
    assert out["results"]
    assert out["results"][0]["decision"] == "pick"
    assert out["results"][0]["guid"] == "z"
