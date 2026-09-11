"""Memory-transport tests: pipe write/read/backpressure/accounting with
synthesized pipe states, a true record-threading chain, and a
request-bytes -> pipe -> serve -> pipe -> response-bytes loopback."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import (
    BYTES,
    REC,
    U64,
    backends_to_test,
    call_many,
    check_cases,
    rec_field,
    require_returned,
    vval,
)

SOURCE = "src/web/transport.mncs"
MOD = "web.transport.v1"


def pipe_bytes(data, length, read_pos=0):
    full = bytes(data) + b"\x00" * (1024 - len(data))
    assert len(full) == 1024
    return REC("web.transport.v1", "Pipe", [
        ("data", {"sequence": {"values": [{"byte": {"value": b}} for b in full]}}),
        ("length", U64(length)),
        ("read_pos", U64(read_pos)),
    ])


def fresh_pipe():
    return pipe_bytes(b"", 0)


def run(calls, backend):
    return check_cases(call_many(SOURCE, MOD, calls, backend))


def read_result(case):
    got = vval(require_returned(case, "pipe"))
    return got


@pytest.mark.parametrize("backend", backends_to_test())
def test_pipe_write_read_accounting(backend):
    hello = pipe_bytes(b"hello world", 11)
    full = pipe_bytes(b"A" * 1020, 1020)
    calls = [
        ("write-fresh", "pipe_write", [fresh_pipe(), BYTES(b"ABC"), U64(3)]),
        ("write-empty", "pipe_write", [fresh_pipe(), BYTES(b""), U64(0)]),
        ("write-blocked", "pipe_write", [full, BYTES(b"12345"), U64(5)]),
        ("read-data", "pipe_read", [hello, U64(5)]),
        ("read-all", "pipe_read", [hello, U64(100)]),
        ("read-empty", "pipe_read", [fresh_pipe(), U64(10)]),
        ("avail", "pipe_available", [pipe_bytes(b"abcdef", 6, read_pos=2)]),
        ("free", "pipe_free", [pipe_bytes(b"abcdef", 6)]),
    ]
    cases = run(calls, backend)
    w = read_result(cases["write-fresh"])
    assert w["accepted"] is True and w["blocked"] is False
    assert w["pipe"]["length"] == 3
    assert bytes(w["pipe"]["data"][:3]) == b"ABC"
    w = read_result(cases["write-empty"])
    assert w["accepted"] is True and w["pipe"]["length"] == 0
    w = read_result(cases["write-blocked"])
    assert w["accepted"] is False and w["blocked"] is True
    assert w["pipe"]["length"] == 1020
    r = read_result(cases["read-data"])
    assert r["kind"] == 0 and r["length"] == 5
    assert bytes(r["data"][:5]) == b"hello"
    assert r["pipe"]["read_pos"] == 5
    r = read_result(cases["read-all"])
    assert r["kind"] == 0 and r["length"] == 11
    assert bytes(r["data"][:11]) == b"hello world"
    r = read_result(cases["read-empty"])
    assert r["kind"] == 1 and r["length"] == 0
    assert read_result(cases["avail"]) == 4
    assert read_result(cases["free"]) == 1018


@pytest.mark.parametrize("backend", backends_to_test())
def test_pipe_threading_chain(backend):
    # True record threading across invocations: write, echo the pipe,
    # read twice. Proves record values survive the corpus boundary.
    first = run([("w", "pipe_write", [fresh_pipe(), BYTES(b"hi!"), U64(3)])], backend)
    pipe_after_write = rec_field(first["w"]["returned"][0], "pipe")
    second = run([("r1", "pipe_read", [pipe_after_write, U64(2)])], backend)
    r1 = read_result(second["r1"])
    assert r1["kind"] == 0 and bytes(r1["data"][:2]) == b"hi"
    pipe_after_r1 = rec_field(second["r1"]["returned"][0], "pipe")
    third = run([("r2", "pipe_read", [pipe_after_r1, U64(10)])], backend)
    r2 = read_result(third["r2"])
    assert r2["kind"] == 0 and bytes(r2["data"][:1]) == b"!"
    pipe_after_r2 = rec_field(third["r2"]["returned"][0], "pipe")
    fourth = run([("r3", "pipe_read", [pipe_after_r2, U64(10)])], backend)
    assert read_result(fourth["r3"])["kind"] == 1


@pytest.mark.parametrize("backend", backends_to_test())
def test_pipe_loopback(backend):
    # Client bytes -> request pipe -> serve -> response pipe -> bytes.
    # serve_bytes is the oracle; the pipes must transport it losslessly.
    request = b"GET /health HTTP/1.1\r\nHost: h\r\n\r\n"
    served = check_cases(call_many(
        "src/web/app.mncs", "web.app.v1",
        [("s", "serve_bytes",
          [BYTES(request), U64(len(request)),
           U64(512), U64(512), U64(32), U64(1024), U64(1024)])],
        backend))
    enc = vval(require_returned(served["s"], "serve"))
    assert enc["truncated"] is False
    expected = bytes(enc["data"][: enc["length"]])
    assert expected.startswith(b"HTTP/1.1 200 OK\r\n")
    # Request leg.
    put = run([("w", "pipe_write", [fresh_pipe(), BYTES(request), U64(len(request))])],
              backend)
    pipe_req = rec_field(put["w"]["returned"][0], "pipe")
    get = run([("r", "pipe_read", [pipe_req, U64(256)])], backend)
    r1 = read_result(get["r"])
    assert r1["kind"] == 0
    assert bytes(r1["data"][: r1["length"]]) == request
    # Response leg.
    put = run([("w", "pipe_write",
                [fresh_pipe(), BYTES(expected), U64(len(expected))])], backend)
    pipe_resp = rec_field(put["w"]["returned"][0], "pipe")
    get = run([("r", "pipe_read", [pipe_resp, U64(256)])], backend)
    r2 = read_result(get["r"])
    assert r2["kind"] == 0
    assert bytes(r2["data"][: r2["length"]]) == expected
