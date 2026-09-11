"""Round-trip laws: parse -> encode -> parse converges to the same model,
and encoder -> parser preserves status/body bytes."""

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

SOURCE = "src/web/roundtrip.mncs"
MOD = "web.roundtrip.v1"
DEF = [U64(512), U64(512), U64(32), U64(1024), U64(1024)]

REQUESTS = [
    b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
    b"GET / HTTP/1.0\r\nHost: h\r\n\r\n",
    b"POST /a?x=1 HTTP/1.1\r\nHost: h\r\nX-E: \r\nX-O:   v\t \r\n\r\n",
    b"BREW /thing HTTP/1.1\r\n\r\n",
    b"OPTIONS * HTTP/1.1\r\n\r\n",
    b"POST /items HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n\r\nhello",
    b"POST /x HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
    b"POST /x HTTP/1.1\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc",
    b"POST /x HTTP/1.1\r\ncontent-length: 4\r\n\r\nabcd",
    b"GET / HTTP/1.1\r\nX-A: b:c\r\n\r\n",
    b"GET /s?a=1&a=2 HTTP/1.1\r\n\r\n",
    b"GET / HTTP/1.1\r\nTransfer-Encoding:\r\n\r\n",
    b"PUT /big HTTP/1.1\r\nHost: h\r\nA: 1\r\nB: 2\r\nC: 3\r\nD: 4\r\nE: 5\r\n\r\n",
]

RESPONSES = [
    # code, content_type, body
    (200, 2, b'{"status":"ok"}'),
    (201, 2, b'{"created":true}'),
    (204, 0, b""),
    (404, 1, b""),
    (500, 1, b"boom"),
    (418, 2, b"teapot"),
    (505, 1, b""),
    (200, 0, b"x" * 200),
]


def body256(raw):
    data = bytes(raw)
    assert len(data) <= 256
    return {"sequence": {"values": [{"byte": {"value": b}} for b in data] + [{"byte": {"value": 0}}] * (256 - len(data))}}


@pytest.mark.parametrize("backend", backends_to_test())
def test_request_roundtrip(backend):
    calls = [(f"req-{i}", "request_roundtrip", [BYTES(raw), U64(len(raw))] + DEF, 1000000)
             for i, raw in enumerate(REQUESTS)]
    # Negative: chunked framing fails parsing, so the law reports the
    # parse error instead of converging.
    te = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
    calls.append(("req-te", "request_roundtrip", [BYTES(te), U64(len(te))] + DEF, 1000000))
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for i, _raw in enumerate(REQUESTS):
        got = vval(require_returned(cases[f"req-{i}"], "roundtrip"))
        assert got == 0, f"request {i}: law code {got}"
    # Law tiers in request_roundtrip: 1xxx = first parse failed
    # (kind*10 + error), 3xxx = re-parse failed, 4xxx/5xxx = truncation.
    # TE-chunked fails the first parse with kind 2, error 16
    # (UnsupportedTransfer), hence 1036.
    te_code = vval(require_returned(cases["req-te"], "roundtrip"))
    assert te_code == 1000 + 20 + 16, te_code


@pytest.mark.parametrize("backend", backends_to_test())
def test_response_roundtrip(backend):
    calls = [(f"resp-{i}", "response_roundtrip",
              [U16(code), U64(ct), body256(body), U64(len(body))], 500000)
             for i, (code, ct, body) in enumerate(RESPONSES)]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for i, _spec in enumerate(RESPONSES):
        got = vval(require_returned(cases[f"resp-{i}"], "roundtrip"))
        assert got == 0, f"response {i}: law code {got}"
