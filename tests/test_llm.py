import httpx

from librarian.identify import Identity, identify_completed
from librarian.llm import LLMClient, merge_llm_identity, parse_json_object


def test_parse_json_object_fenced():
    payload = parse_json_object('```json\n{"kind": "book", "title": "Dune"}\n```')
    assert payload == {"kind": "book", "title": "Dune"}


def test_merge_drops_invented_isbn():
    identity = Identity(kind="book", title="Dune", author="Herbert", confidence="low")
    evidence = "folder: Dune.1977 files: Dune.epub indexer_isbn: "
    merged = merge_llm_identity(
        identity,
        {
            "kind": "book",
            "title": "Dune",
            "author_or_artist": "Herbert",
            "isbn": "9780441172719",
            "confidence": 0.99,
        },
        evidence,
    )
    assert merged.isbn == ""
    assert merged.confidence == "low"


def test_merge_keeps_isbn_present_in_evidence():
    identity = Identity(kind="book", title="Dune", author="Herbert", isbn="", confidence="low")
    evidence = "indexer_isbn: 9780441172719 folder: Dune"
    merged = merge_llm_identity(
        identity,
        {
            "kind": "book",
            "title": "Dune",
            "author_or_artist": "Herbert",
            "isbn": "9780441172719",
            "confidence": 0.9,
        },
        evidence,
    )
    assert merged.isbn == "9780441172719"
    assert merged.confidence == "high"


def test_identify_completed_calls_llm_when_low(tmp_path):
    folder = tmp_path / "Mystery.Release"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"epub")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"kind":"comic","title":"Saga #1","series":"Saga","issue":"1","isbn":null,"confidence":0.9,"rationale":"series parse"}'
                        }
                    }
                ]
            },
        )

    client = LLMClient("http://llm.example/v1", "k", "gpt-test", transport=httpx.MockTransport(handler))
    result = identify_completed(folder, llm_client=client)
    assert result["identity"]["kind"] == "comic"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"
    assert result["identity"]["isbn"] == ""
    assert result["auto_organize"] is True


def test_llm_unknown_stays_review(tmp_path):
    folder = tmp_path / "nope"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"epub")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"kind":"unknown","confidence":0.1}'}}]},
        )

    client = LLMClient("http://llm.example/v1", "k", "gpt-test", transport=httpx.MockTransport(handler))
    result = identify_completed(folder, llm_client=client)
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "unknown_identity"
