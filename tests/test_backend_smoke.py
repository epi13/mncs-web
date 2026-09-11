"""Backend portability smoke: every layer executes on every backend.

The full suite runs on the fast backends (bytecode, wasm) for iteration
speed. This file runs a thin slice — one case per layer — across the
whole matrix (set MNCS_BACKENDS explicitly) to prove no layer depends
on backend-specific behavior.
"""

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

RAW = b"GET /health HTTP/1.1\r\nHost: h\r\n\r\n"


@pytest.mark.parametrize("backend", backends_to_test())
def test_backend_smoke(backend):
    leaves = check_cases(call_many(
        "src/web/limits.mncs", "web.limits.v1",
        [("wire", "static_wire", [])], backend))
    assert vval(require_returned(leaves["wire"], "smoke")) == 1024

    parsed = check_cases(call_many(
        "src/web/parser.mncs", "web.parser.v1",
        [("get", "parse_default", [BYTES(RAW), U64(len(RAW))])], backend))
    got = vval(require_returned(parsed["get"], "smoke"))
    assert got["kind"] == 0 and got["consumed"] == len(RAW), got

    served = check_cases(call_many(
        "src/web/app.mncs", "web.app.v1",
        [("s", "serve_bytes",
          [BYTES(RAW), U64(len(RAW)),
           U64(512), U64(512), U64(32), U64(1024), U64(1024)])], backend))
    enc = vval(require_returned(served["s"], "smoke"))
    assert enc["truncated"] is False
    wire = bytes(enc["data"][: enc["length"]])
    assert wire == (
        b"HTTP/1.1 200 OK\r\nContent-Length: 15\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b'{"status":"ok"}'
    ), wire
