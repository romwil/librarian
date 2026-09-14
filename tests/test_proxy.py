from fastapi import Request

from librarian.proxy import request_is_trusted_https, trust_proxy_headers
from librarian.rate_limit import client_ip


def _request(*, forwarded_proto=None, forwarded_for=None, client_host="127.0.0.1", scheme="http"):
    headers = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 12345) if client_host else None,
        "server": ("test", 80),
    }
    return Request(scope)


def test_trust_proxy_default_off(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    assert trust_proxy_headers() is False


def test_trust_proxy_opt_in(monkeypatch):
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    assert trust_proxy_headers() is True
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "yes")
    assert trust_proxy_headers() is True
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "0")
    assert trust_proxy_headers() is False


def test_untrusted_forwarded_proto_never_sets_https(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    req = _request(forwarded_proto="https", client_host="10.10.1.50")
    assert request_is_trusted_https(req) is False
    assert request_is_trusted_https(None) is False


def test_trusted_forwarded_proto_is_https(monkeypatch):
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    req = _request(forwarded_proto="https, http", client_host="172.17.0.1")
    assert request_is_trusted_https(req) is True
    http_only = _request(forwarded_proto="http", client_host="172.17.0.1")
    assert request_is_trusted_https(http_only) is False


def test_socket_https_is_trusted_without_proxy_flag(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    req = _request(scheme="https", client_host="10.10.1.50")
    assert request_is_trusted_https(req) is True


def test_untrusted_xff_ignored_for_client_ip(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    req = _request(forwarded_for="198.51.100.9", client_host="127.0.0.1")
    assert client_ip(req) == "127.0.0.1"


def test_trusted_xff_used_for_client_ip(monkeypatch):
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    req = _request(forwarded_for="198.51.100.9, 10.0.0.1", client_host="172.17.0.1")
    assert client_ip(req) == "198.51.100.9"
