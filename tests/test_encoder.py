"""Response/request encoder tests: byte-exact wire output.

Expected bytes are written by hand from RFC 9110 framing (independent
oracle: Python string construction, never MNCS logic).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import (
    BYTES,
    U16,
    U64,
    backends_to_test,
    call_many,
    check_cases,
    require_returned,
    vval,
)

SOURCE = "src/web/encode.mncs"
MOD = "web.encode.v1"


def body256(raw):
    data = bytes(raw)
    assert len(data) <= 256
    return {"sequence": {"values": [{"byte": {"value": b}} for b in data] + [{"byte": {"value": 0}}] * (256 - len(data))}}


def run(calls, backend):
    return check_cases(call_many(SOURCE, MOD, calls, backend))


def wire(case):
    got = vval(require_returned(case, "encode"))
    assert got["truncated"] is False
    return bytes(got["data"][: got["length"]])


@pytest.mark.parametrize("backend", backends_to_test())
def test_respond_byte_exact(backend):
    calls = [
        ("ok", "respond", [U16(200), U64(2), body256(b"OK"), U64(2)]),
        ("notfound", "respond", [U16(404), U64(1), body256(b""), U64(0)]),
        ("server", "respond", [U16(501), U64(0), body256(b""), U64(0)]),
        ("toolong", "respond", [U16(414), U64(2), body256(b"x" * 200), U64(200)]),
    ]
    cases = run(calls, backend)
    assert wire(cases["ok"]) == (
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\nOK"
    )
    assert wire(cases["notfound"]) == (
        b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n"
        b"Content-Type: text/plain\r\nConnection: close\r\n\r\n"
    )
    assert wire(cases["server"]) == (
        b"HTTP/1.1 501 Not Implemented\r\nContent-Length: 0\r\n"
        b"Connection: close\r\n\r\n"
    )
    got = wire(cases["toolong"])
    assert got.startswith(
        b"HTTP/1.1 414 URI Too Long\r\nContent-Length: 200\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
    )
    assert got.endswith(b"x" * 200)


@pytest.mark.parametrize("backend", backends_to_test())
def test_encode_large_body(backend):
    # The 1024-byte output buffer caps encodable bodies: a 900-byte body
    # fits exactly (4-digit Content-Length is unreachable through public
    # API — headers always push it over), while 1024 saturates honestly.
    big = bytes((i * 7) % 251 for i in range(1024))
    calls = [
        ("big900", "encode_response_view",
         [U64(1), U16(200), U64(0), BYTES(big[:900]), U64(900)], 500000),
        ("big1024", "encode_response_view",
         [U64(1), U16(200), U64(0), BYTES(big), U64(1024)], 500000),
    ]
    cases = run(calls, backend)
    got = wire(cases["big900"])
    assert got.startswith(
        b"HTTP/1.1 200 OK\r\nContent-Length: 900\r\nConnection: close\r\n\r\n"
    )
    assert got.split(b"\r\n\r\n", 1)[1] == big[:900]
    sat = vval(require_returned(cases["big1024"], "encode"))
    assert sat["truncated"] is True, sat


@pytest.mark.parametrize("backend", backends_to_test())
def test_encode_empty_body_variants(backend):
    calls = [
        ("nocontent", "encode_response", [U64(1), U16(204), U64(0), body256(b""), U64(0)]),
        ("v10", "encode_response", [U64(0), U16(200), U64(1), body256(b""), U64(0)]),
    ]
    cases = run(calls, backend)
    assert wire(cases["nocontent"]) == (
        b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n"
        b"Connection: close\r\n\r\n"
    )
    assert wire(cases["v10"]) == (
        b"HTTP/1.0 200 OK\r\nContent-Length: 0\r\n"
        b"Content-Type: text/plain\r\nConnection: close\r\n\r\n"
    )
