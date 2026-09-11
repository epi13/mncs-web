"""HTTP parser tests: valid/incomplete/malformed/limit/response batteries.

Incomplete inputs are exercised by re-parsing the full message with a
short `buflen`: every proper prefix of a valid message must report
kind 1, which is exactly the verdict an incremental host would act on.
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
    slice_span,
    vval,
)

SOURCE = "src/web/parser.mncs"
MOD = "web.parser.v1"
DEF = [U64(512), U64(512), U64(32), U64(1024), U64(1024)]
TINY = [U64(16), U64(16), U64(2), U64(32), U64(8)]

MIN_GET = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"


def preq(raw, buflen=None, lims=None):
    lims = DEF if lims is None else lims
    return ["parse_request", [BYTES(raw), U64(len(raw) if buflen is None else buflen)] + lims]


def presp(raw, buflen=None, lims=None):
    lims = DEF if lims is None else lims
    return ["parse_response", [BYTES(raw), U64(len(raw) if buflen is None else buflen)] + lims]


def out(case):
    return vval(require_returned(case, "parse"))


def assert_head(t, raw, head, method, path, version, headers, body=b"",
                cl_found=False, cl=0):
    assert head["method"] == method, f"{t}: method {head['method']}"
    got_path = slice_span(raw, head["target"]["path_start"], head["target"]["path_len"])
    assert got_path == path, f"{t}: path {got_path!r}"
    assert head["version"] == version, f"{t}: version"
    block = head["headers"]
    assert block["count"] == len(headers), f"{t}: nheaders {block['count']}"
    for i, (want_name, want_value) in enumerate(headers):
        h = block["headers"][i]
        name = slice_span(raw, h["name_start"], h["name_len"])
        value = slice_span(raw, h["value_start"], h["value_len"])
        assert name == want_name, f"{t}: header {i} name {name!r}"
        assert value == want_value, f"{t}: header {i} value {value!r}"
    assert head["has_content_length"] is cl_found, f"{t}: cl flag"
    assert head["content_length"] == cl, f"{t}: cl value"
    got_body = slice_span(raw, head["body_start"], head["body_len"])
    assert got_body == body, f"{t}: body {got_body!r}"


VALID = [
    ("min-get", MIN_GET, 0, b"/", 1,
     [(b"Host", b"example.com")], b""),
    ("http10", b"GET / HTTP/1.0\r\nHost: h\r\n\r\n", 0, b"/", 0,
     [(b"Host", b"h")], b""),
    ("multi", b"POST /a?x=1 HTTP/1.1\r\nHost: h\r\nX-E: \r\nX-O:   v\t \r\n\r\n",
     1, b"/a", 1, [(b"Host", b"h"), (b"X-E", b""), (b"X-O", b"v")], b""),
    ("ext", b"BREW /thing HTTP/1.1\r\n\r\n", 9, b"/thing", 1, [], b""),
    ("asterisk", b"OPTIONS * HTTP/1.1\r\n\r\n", 5, b"*", 1, [], b""),
    ("post-body", b"POST /items HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n\r\nhello",
     1, b"/items", 1, [(b"Host", b"h"), (b"Content-Length", b"5")], b"hello"),
    ("cl-zero", b"POST /x HTTP/1.1\r\nContent-Length: 0\r\n\r\n", 1, b"/x", 1,
     [(b"Content-Length", b"0")], b""),
    ("dup-cl-same",
     b"POST /x HTTP/1.1\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc",
     1, b"/x", 1, [(b"Content-Length", b"3"), (b"Content-Length", b"3")], b"abc"),
    ("case-cl", b"POST /x HTTP/1.1\r\ncontent-length: 4\r\n\r\nabcd",
     1, b"/x", 1, [(b"content-length", b"4")], b"abcd"),
    ("colon-value", b"GET / HTTP/1.1\r\nX-A: b:c\r\n\r\n", 0, b"/", 1,
     [(b"X-A", b"b:c")], b""),
    ("query-multi", b"GET /s?a=1&a=2 HTTP/1.1\r\n\r\n", 0, b"/s", 1, [], b""),
    ("te-empty", b"GET / HTTP/1.1\r\nTransfer-Encoding:\r\n\r\n", 0, b"/", 1,
     [(b"Transfer-Encoding", b"")], b""),
]


@pytest.mark.parametrize("backend", backends_to_test())
def test_valid_requests(backend):
    calls = []
    for cid, raw, _m, _p, _v, _h, _b in VALID:
        fn, args = preq(raw)
        calls.append((cid, fn, args))
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, raw, method, path, version, headers, body in VALID:
        got = out(cases[cid])
        assert got["kind"] == 0, f"{cid}: kind {got['kind']} err {got['error']}"
        assert got["error"] == 0, cid
        assert got["consumed"] == len(raw), f"{cid}: consumed {got['consumed']}"
        assert got["is_response"] is False, cid
        cl = [(n, v) for n, v in headers
              if n.lower() == b"content-length"]
        assert_head(cid, raw, got["head"], method, path, version, headers,
                    body, cl_found=bool(cl),
                    cl=int(cl[0][1]) if cl else 0)
        if method == 9:
            ext = slice_span(raw, got["head"]["ext_start"], got["head"]["ext_len"])
            assert ext == raw.split(b" ")[0], f"{cid}: ext {ext!r}"


@pytest.mark.parametrize("backend", backends_to_test())
def test_prefixes_are_incomplete(backend):
    cuts = [0, 1, 2, 3, 5, 10, 14, 15, 16, 20, 26, 30, 35, 36]
    calls = [(f"cut-{k}", *preq(MIN_GET, buflen=k)) for k in cuts]
    short = b"POST /items HTTP/1.1\r\nContent-Length: 5\r\n\r\nhel"
    calls.append(("body-short", *preq(short)))
    calls.append(("nolines", *preq(b"GET / HTTP/1.1\r\n")))
    calls.append(("cr-last", *preq(b"GET / HTTP/1.1\r\nHost: h\r")))
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, _fn, _args in calls:
        got = out(cases[cid])
        assert got["kind"] == 1, f"{cid}: kind {got['kind']} err {got['error']}"
        assert got["consumed"] == 0, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_malformed_requests(backend):
    vectors = [
        # "GE" is a well-formed EXT token, so the space-split method
        # surfaces as a bad version token, not a bad method.
        ("split-method", b"GE T / HTTP/1.1\r\n\r\n", 3),
        ("empty-method", b" / HTTP/1.1\r\n\r\n", 4),
        ("method-ctl", b"G\x01T / HTTP/1.1\r\n\r\n", 1),
        ("bad-target-ctl", b"GET /\x01 HTTP/1.1\r\n\r\n", 2),
        ("absolute", b"GET http://h/x HTTP/1.1\r\n\r\n", 2),
        ("bad-version", b"GET / HTTP/2.0\r\n\r\n", 3),
        ("short-version", b"GET / HTTP/1\r\n\r\n", 3),
        ("version-sp", b"GET / HTTP/1.1 \r\n\r\n", 3),
        ("lf-only", b"GET / HTTP/1.1\n\n", 4),
        ("bare-cr", b"GET / HTTP/1.1\rX", 5),
        ("no-colon", b"GET / HTTP/1.1\r\nNoColon\r\n\r\n", 7),
        ("empty-name", b"GET / HTTP/1.1\r\n: v\r\n\r\n", 6),
        ("sp-before-colon", b"GET / HTTP/1.1\r\nN : v\r\n\r\n", 6),
        ("lead-space", b"GET / HTTP/1.1\r\n v: x\r\n\r\n", 5),
        ("bad-cl-alpha", b"POST /x HTTP/1.1\r\nContent-Length: abc\r\n\r\n", 8),
        ("bad-cl-empty", b"POST /x HTTP/1.1\r\nContent-Length:\r\n\r\n", 8),
        ("bad-cl-over", b"POST /x HTTP/1.1\r\nContent-Length: 4294967296\r\n\r\n", 8),
        ("bad-cl-huge", b"POST /x HTTP/1.1\r\nContent-Length: 99999999999\r\n\r\n", 8),
        ("cl-conflict",
         b"POST /x HTTP/1.1\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\nhello!", 8),
        ("te-chunked", b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n", 16),
        ("te-gzip", b"GET / HTTP/1.1\r\nTransfer-Encoding: gzip\r\n\r\n", 16),
    ]
    calls = [(cid, *preq(raw)) for cid, raw, _ in vectors]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, _raw, code in vectors:
        got = out(cases[cid])
        assert got["kind"] == 2, f"{cid}: kind {got['kind']}"
        assert got["error"] == code, f"{cid}: error {got['error']}"
        assert got["consumed"] == 0, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_limit_enforcement(backend):
    long_path = b"GET /" + b"a" * 30 + b" HTTP/1.1\r\n\r\n"
    long_hdr = b"GET / HTTP/1.1\r\nX: " + b"b" * 20 + b"\r\n\r\n"
    many = b"GET / HTTP/1.1\r\nA: 1\r\nB: 2\r\nC: 3\r\n\r\n"
    big = b"GET / HTTP/1.1\r\nA: b\r\nC: d\r\nE: f\r\n\r\n"
    body9 = b"POST /x HTTP/1.1\r\nContent-Length: 9\r\n\r\n123456789"
    body2k = b"POST /x HTTP/1.1\r\nContent-Length: 2000\r\n\r\n"
    # NOTE: tiny's 16-byte line caps cannot even hold a Content-Length
    # header (shortest is 17 chars), so body-cap uses custom limits with
    # generous lines but max_body 8.
    vectors = [
        ("long-start", long_path, TINY, 9),
        ("long-header", long_hdr, TINY, 10),
        ("many-headers", many, TINY, 11),
        ("big-head", big, [U64(512), U64(512), U64(32), U64(32), U64(1024)], 12),
        ("body-cap", body9, [U64(512), U64(512), U64(32), U64(1024), U64(8)], 13),
        ("cl-huge-body", body2k, DEF, 13),
    ]
    calls = [(cid, *preq(raw, lims=lims)) for cid, raw, lims, _ in vectors]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, _raw, _lims, code in vectors:
        got = out(cases[cid])
        assert got["kind"] == 2, f"{cid}: kind {got['kind']}"
        assert got["error"] == code, f"{cid}: error {got['error']}"


@pytest.mark.parametrize("backend", backends_to_test())
def test_responses(backend):
    r200 = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
    vectors = [
        ("resp-min", r200, 0, 200, b"OK", b"OK"),
        ("resp-404", b"HTTP/1.0 404 Not Found\r\n\r\n", 0, 404, b"Not Found", b""),
        ("resp-empty-reason", b"HTTP/1.1 200\r\n\r\n", 0, 200, b"", b""),
        ("resp-badcode", b"HTTP/1.1 99 X\r\n\r\n", 14, 0, b"", b""),
        ("resp-code600", b"HTTP/1.1 600 X\r\n\r\n", 14, 0, b"", b""),
        ("resp-nocode", b"HTTP/1.1 OK\r\n\r\n", 14, 0, b"", b""),
        ("resp-badver", b"HTTP/2.0 200 OK\r\n\r\n", 3, 0, b"", b""),
    ]
    calls = [(cid, *presp(raw)) for cid, raw, *_ in vectors]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    for cid, raw, code, status, reason, body in vectors:
        got = out(cases[cid])
        if code == 0:
            assert got["kind"] == 0, f"{cid}: {got['kind']} {got['error']}"
            assert got["is_response"] is True, cid
            resp = got["response"]
            assert resp["status"] == status, cid
            assert slice_span(raw, resp["reason_start"], resp["reason_len"]) == reason, cid
            assert slice_span(raw, resp["body_start"], resp["body_len"]) == body, cid
            assert got["consumed"] == len(raw), cid
        else:
            assert got["kind"] == 2 and got["error"] == code, f"{cid}: {got}"


@pytest.mark.parametrize("backend", backends_to_test())
def test_direction_cross_checks(backend):
    r200 = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
    calls = [("req-as-resp", *presp(MIN_GET)), ("resp-as-req", *preq(r200))]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    assert out(cases["req-as-resp"])["error"] == 3
    assert out(cases["resp-as-req"])["error"] == 1


@pytest.mark.parametrize("backend", backends_to_test())
def test_pipelined_prefix_consumed(backend):
    extra = b"GET /second HTTP/1.1\r\n\r\n"
    raw = (b"POST /items HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello" + extra)
    head_len = len(raw) - len(extra)
    calls = [("pipelined", *preq(raw))]
    cases = check_cases(call_many(SOURCE, MOD, calls, backend))
    got = out(cases["pipelined"])
    assert got["kind"] == 0, got
    assert got["consumed"] == head_len, got
    assert slice_span(raw, got["head"]["body_start"], got["head"]["body_len"]) == b"hello"
