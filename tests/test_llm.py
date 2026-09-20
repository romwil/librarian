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


def test_looks_like_dump_title_dotted_usenet():
    from librarian.identify import looks_like_dump_title

    assert looks_like_dump_title(
        "102.Minutes.The.Untold.Story.of.the.Fight.to.Survive.Inside.the.Twin.Towers.Audio.book.MP3"
    )
    assert looks_like_dump_title(
        "102 Minutes The Untold Story of the Fight to Survive Inside the Twin Towers Audio book"
    )
    assert not looks_like_dump_title("Piranesi")


def test_merge_replaces_dump_title_and_fills_author():
    identity = Identity(
        kind="audiobook",
        title="102.Minutes.The.Untold.Story.of.the.Fight.to.Survive.Inside.the.Twin.Towers.Audio.book",
        author="",
        confidence="low",
        review_reason="unknown_identity",
    )
    evidence = (
        "folder: 102.Minutes.The.Untold.Story.of.the.Fight.to.Survive.Inside.the.Twin.Towers.Audio.book\n"
        "files: chapter01.mp3\n"
        "indexer_isbn: \n"
    )
    merged = merge_llm_identity(
        identity,
        {
            "kind": "audiobook",
            "title": "102 Minutes: The Untold Story of the Fight to Survive Inside the Twin Towers",
            "author_or_artist": "Jim Dwyer",
            "isbn": "9780805076820",
            "confidence": 0.92,
            "rationale": "dotted dump",
        },
        evidence,
    )
    assert merged.isbn == ""
    assert merged.title.startswith("102 Minutes")
    assert "." not in merged.title
    assert merged.author == "Jim Dwyer"
    assert merged.kind == "audiobook"
    assert merged.confidence == "high"
    assert merged.review_reason is None


def test_identify_completed_audio_book_hint_calls_llm(tmp_path):
    folder = tmp_path / "102.Minutes.The.Untold.Story.Audio.book"
    folder.mkdir()
    (folder / "01.mp3").write_bytes(b"ID3")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert "102.Minutes" in body or "Audio.book" in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"kind":"audiobook","title":"102 Minutes",'
                                '"author_or_artist":"Jim Dwyer","isbn":null,'
                                '"confidence":0.9,"rationale":"audiobook dump"}'
                            )
                        }
                    }
                ]
            },
        )

    client = LLMClient("http://llm.example/v1", "k", "gpt-test", transport=httpx.MockTransport(handler))
    result = identify_completed(folder, llm_client=client)
    assert result["identity"]["kind"] == "audiobook"
    assert result["identity"]["title"] == "102 Minutes"
    assert result["identity"]["author"] == "Jim Dwyer"
    assert result["identity"]["isbn"] == ""
    assert result["auto_organize"] is True


def test_friendly_llm_error_maps_429():
    from librarian.llm import LLM_RATE_LIMIT_COPY, LLMError, friendly_llm_error

    assert friendly_llm_error(LLMError("LLM HTTP 429", status_code=429)) == LLM_RATE_LIMIT_COPY
    assert friendly_llm_error(RuntimeError("upstream rate-limited")) == LLM_RATE_LIMIT_COPY
    assert "busy" in friendly_llm_error(LLMError("LLM HTTP 503", status_code=503)).lower()


def test_parse_provider_http_error_gemini_bad_key():
    from librarian.llm import LLM_BAD_KEY_COPY, LLMError, parse_provider_http_error

    response = httpx.Response(
        400,
        json={
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            }
        },
    )
    message = parse_provider_http_error(response)
    assert message == LLM_BAD_KEY_COPY
    assert "API key not valid" not in message
    assert "Please pass a valid API key" not in message


def test_chat_raw_surfaces_gemini_400_body(monkeypatch):
    from librarian.llm import LLM_BAD_KEY_COPY, LLMClient, LLMError, reset_llm_rate_limit_state

    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "generateContent" in str(request.url)
        return httpx.Response(
            400,
            json={"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}},
        )

    client = LLMClient(
        "https://generativelanguage.googleapis.com/v1beta",
        "bad-key",
        "gemini-2.5-flash",
        provider="gemini",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    try:
        client.chat_raw(system="s", user="u")
        assert False, "expected LLMError"
    except LLMError as error:
        assert error.status_code == 400
        assert str(error) == LLM_BAD_KEY_COPY
    reset_llm_rate_limit_state()


def test_chat_raw_gemini_success_shaped_response(monkeypatch):
    from librarian.llm import LLMClient, reset_llm_rate_limit_state

    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"display_name":"Hardcover Fiction","published_date":"2026-09-01",'
                                        '"books":[{"rank":1,"title":"Piranesi","author":"Susanna Clarke","isbn":""}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = LLMClient(
        "https://generativelanguage.googleapis.com/v1beta",
        "AIzaSyFake",
        "gemini-2.5-flash",
        provider="gemini",
        transport=httpx.MockTransport(handler),
    )
    text = client.chat_raw(system="lists", user="hardcover fiction")
    assert "Piranesi" in text
    reset_llm_rate_limit_state()


def test_friendly_llm_error_maps_bare_400():
    from librarian.llm import LLM_BAD_KEY_COPY, LLMError, friendly_llm_error

    assert friendly_llm_error(LLMError("LLM HTTP 400", status_code=400)) == LLM_BAD_KEY_COPY

def test_chat_raw_retries_429_with_retry_after(monkeypatch):
    from librarian.llm import LLM_RATE_LIMIT_COPY, LLMClient, LLMError, reset_llm_rate_limit_state

    reset_llm_rate_limit_state()
    sleeps = []
    monkeypatch.setattr("librarian.llm.time.sleep", lambda seconds: sleeps.append(seconds))
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0.05"}, json={"error": "slow down"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client = LLMClient(
        "http://llm.example/v1",
        "k",
        "gpt-test",
        transport=httpx.MockTransport(handler),
        max_retries=2,
    )
    assert client.chat_raw(system="s", user="u") == "ok"
    assert attempts["n"] == 2
    assert sleeps and sleeps[0] >= 0.05
    reset_llm_rate_limit_state()


def test_chat_raw_exhausts_429_and_sets_cooldown(monkeypatch):
    from librarian.llm import LLM_RATE_LIMIT_COPY, LLMClient, LLMError, reset_llm_rate_limit_state

    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "nope"})

    client = LLMClient(
        "http://llm.example/v1",
        "k",
        "gpt-test",
        transport=httpx.MockTransport(handler),
        max_retries=1,
    )
    try:
        client.chat_raw(system="s", user="u")
        assert False, "expected LLMError"
    except LLMError as error:
        assert error.status_code == 429
        assert str(error) == LLM_RATE_LIMIT_COPY
        assert error.rate_limited
    reset_llm_rate_limit_state()
