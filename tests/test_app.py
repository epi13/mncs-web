"""Application slice tests: serve_once model verdicts and serve_bytes
wire output, including error mapping and the param-length refusal."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import (
    BYTES,
    U64,
    backends_to_test,
    call_many,
    check_cases,
    require_returned,
    vval,
)

SOURCE = "src/web/app.mncs"
MOD = "web.app.v1"
DEF = [U64(512), U64(512), U64(32), U64(1024), U64(1024)]


def serve(raw, lims=None):
    lims = DEF if lims is None else lims
    return ["serve_once", [BYTES(raw), U64(len(raw))] + lims]


def serve_wire(raw, lims=None):
    lims = DEF if lims is None else lims
    return ["serve_bytes", [BYTES(raw), U64(len(raw))] + lims]


def model(case):
    return vval(require_returned(case, "serve"))


def wire(case):
    got = vval(require_returned(case, "serve"))
    assert got["truncated"] is False
    return got["status"] if "status" in got else None, bytes(got["data"][: got["length"]])


@pytest.mark.parametrize("backend", backends_to_test())
def test_serve_models(backend):
    long_id = b"u" * 300
    vectors = [
        # id, raw, status, handler, error, body
        ("health", b"GET /health HTTP/1.1\r\nHost: h\r\n\r\n",
         200, 0, 0, b'{"status":"ok"}'),
        ("users", b"GET /users HTTP/1.1\r\n\r\n", 200, 1, 0, b'{"users":[]}'),
        ("user", b"GET /users/42 HTTP/1.1\r\n\r\n", 200, 2, 0, b'{"id":"42"}'),
        ("items", b"POST /items HTTP/1.1\r\nContent-Length: 2\r\n\r\nhi",
         201, 3, 0, b'{"created":true}'),
        ("version", b"GET /version HTTP/1.1\r\n\r\n", 200, 4, 0, b'{"web":"0.1.0"}'),
        ("miss", b"GET /nope HTTP/1.1\r\n\r\n", 404, 255, 0, b'{"error":404}'),
        ("method-miss", b"POST /health HTTP/1.1\r\n\r\n", 405, 255, 0, b'{"error":405}'),
        ("bad-version", b"GET / HTTP/9.9\r\n\r\n", 505, 255, 3,
         b'{"error":"request rejected"}'),
        ("garbage", b"\x00\x01\x02", 400, 255, 1, b'{"error":"request rejected"}'),
        ("short", b"GET /", 400, 255, 98, b'{"error":"request rejected"}'),
        ("long-id", b"GET /users/" + long_id + b" HTTP/1.1\r\n\r\n",
         414, 2, 13, b'{"error":"request rejected"}'),
    ]
    calls = [(cid, *serve(raw)) for cid, raw, *_ in vectors]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, _raw, status, handler, error, body in vectors:
        got = model(cases[cid])
        assert got["status"] == status, f"{cid}: {got}"
        assert got["handler"] == handler, f"{cid}: handler {got['handler']}"
        assert bytes(got["body"][: got["body_len"]]) == body, f"{cid}: body"
        assert got["error"] == error, f"{cid}: error {got['error']}"
        assert got["content_type"] == 2, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_serve_wire(backend):
    calls = [
        ("health", *serve_wire(b"GET /health HTTP/1.1\r\nHost: h\r\n\r\n")),
        ("user", *serve_wire(b"GET /users/42 HTTP/1.1\r\n\r\n")),
        ("miss", *serve_wire(b"GET /nope HTTP/1.1\r\n\r\n")),
        ("badver", *serve_wire(b"GET / HTTP/9.9\r\n\r\n")),
    ]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    _st, health = wire(cases["health"])
    assert health == (
        b"HTTP/1.1 200 OK\r\nContent-Length: 15\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b'{"status":"ok"}'
    ), health
    _st, user = wire(cases["user"])
    assert user == (
        b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b'{"id":"42"}'
    ), user
    _st, miss = wire(cases["miss"])
    assert miss == (
        b"HTTP/1.1 404 Not Found\r\nContent-Length: 13\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b'{"error":404}'
    ), miss
    _st, badver = wire(cases["badver"])
    assert badver.startswith(b"HTTP/1.1 505 HTTP Version Not Supported\r\n"), badver
