"""Leaf protocol-type unit tests: method, version, status, URI, headers,
message digits, errors, limits.

Every expectation below executes inside mncs-language on each backend;
this file only transports byte views and decodes the results.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import (
    BYTES,
    FIN,
    U16,
    U64,
    backends_to_test,
    call_many,
    check_cases,
    require_returned,
    vval,
)

DL = "src/web/method.mncs"
MOD = "web.method.v1"


def run(source, module, calls, backend):
    return check_cases(call_many(source, module, calls, backend))


def decoded(case):
    return vval(require_returned(case, "case"))


@pytest.mark.parametrize("backend", backends_to_test())
def test_method_parse_maps_all_methods(backend):
    vectors = [
        ("get", b"GET", 0, 0),
        ("post", b"POST", 0, 1),
        ("put", b"PUT", 0, 2),
        ("delete", b"DELETE", 0, 3),
        ("head", b"HEAD", 0, 4),
        ("options", b"OPTIONS", 0, 5),
        ("patch", b"PATCH", 0, 6),
        ("trace", b"TRACE", 0, 7),
        ("connect", b"CONNECT", 0, 8),
        ("ext", b"BREW", 0, 9),
        ("lower", b"get", 0, 9),
        ("empty", b"", 0, 9),
    ]
    calls = [
        (cid, "parse", [BYTES(raw), U64(off), U64(len(raw)), U64(len(raw))])
        for cid, raw, off, _ in vectors
    ]
    cases = run(DL, MOD, calls, backend)
    for cid, _raw, _off, want in vectors:
        got = decoded(cases[cid])
        assert got["discriminant"] == want, f"{cid}: {got}"


@pytest.mark.parametrize("backend", backends_to_test())
def test_method_token_validity(backend):
    vectors = [
        ("ok", b"GET", True),
        ("ext-ok", b"X-CUSTOM", True),
        ("space", b"GE T", False),
        ("empty", b"", False),
        ("slash", b"a/b", False),
        ("ctl", b"GE\x01T", False),
    ]
    # 17-byte token exceeds the 16-byte token bound.
    calls = [
        (cid, "token_valid", [BYTES(raw), U64(0), U64(len(raw)), U64(len(raw))])
        for cid, raw, _ in vectors
    ]
    calls.append(
        ("long", "token_valid", [BYTES(b"A" * 17), U64(0), U64(17), U64(17)])
    )
    cases = run(DL, MOD, calls, backend)
    for cid, _raw, want in vectors:
        assert decoded(cases[cid]) is want, cid
    assert decoded(cases["long"]) is False


@pytest.mark.parametrize("backend", backends_to_test())
def test_method_codes_and_predicates(backend):
    # Finite-typed entry points, threaded through synthesized values.
    names = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS",
             "PATCH", "TRACE", "CONNECT", "EXT"]
    codes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    safe = [True, False, False, False, True, True, False, True, False, False]
    idem = [True, False, True, True, True, True, False, True, False, False]
    calls = []
    for name, disc in zip(names, codes):
        fin = FIN("web.method.v1", "Method", name, disc)
        calls.append((f"code-{name}", "code_of", [fin]))
        calls.append((f"safe-{name}", "is_safe", [fin]))
        calls.append((f"idem-{name}", "is_idempotent", [fin]))
        calls.append((f"text-{name}", "text", [fin]))
    for code in codes:
        calls.append((f"of-{code}", "method_of", [U64(code)]))
    calls.append(("of-99", "method_of", [U64(99)]))
    cases = run(DL, MOD, calls, backend)
    for name, want in zip(names, codes):
        assert decoded(cases[f"code-{name}"]) == want, name
    for name, want in zip(names, safe):
        assert decoded(cases[f"safe-{name}"]) is want, name
    for name, want in zip(names, idem):
        assert decoded(cases[f"idem-{name}"]) is want, name
    spellings = [b"GET", b"POST", b"PUT", b"DELETE", b"HEAD", b"OPTIONS",
                 b"PATCH", b"TRACE", b"CONNECT", b""]
    for name, want, spell in zip(names, [3, 4, 3, 6, 4, 7, 5, 5, 7, 0], spellings):
        text = decoded(cases[f"text-{name}"])
        assert text["length"] == want, name
        assert bytes(text["data"][:want]) == spell, name
    for code in codes:
        assert decoded(cases[f"of-{code}"])["discriminant"] == code
    assert decoded(cases["of-99"])["discriminant"] == 9


@pytest.mark.parametrize("backend", backends_to_test())
def test_version_parse(backend):
    vectors = [
        ("v11", b"HTTP/1.1", 1),
        ("v10", b"HTTP/1.0", 0),
        ("v20", b"HTTP/2.0", 2),
        ("short", b"HTTP/1", 2),
        ("long", b"HTTP/1.12", 2),
        ("empty", b"", 2),
        ("bad-minor", b"HTTP/1.9", 2),
    ]
    calls = [
        (cid, "parse", [BYTES(raw), U64(0), U64(len(raw)), U64(len(raw))])
        for cid, raw, _ in vectors
    ]
    cases = run("src/web/version.mncs", "web.version.v1", calls, backend)
    for cid, _raw, want in vectors:
        assert decoded(cases[cid]) == want, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_status_classes_and_reasons(backend):
    codes = [100, 200, 201, 204, 301, 400, 404, 405, 411, 413, 414,
             418, 431, 500, 501, 505, 99, 600]
    want_class = [1, 2, 2, 2, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 0, 0]
    calls = []
    for code in codes:
        calls.append((f"class-{code}", "class_of", [U16(code)]))
        calls.append((f"valid-{code}", "is_valid", [U16(code)]))
        calls.append((f"reason-{code}", "reason", [U16(code)]))
    cases = run("src/web/status.mncs", "web.status.v1", calls, backend)
    for code, want in zip(codes, want_class):
        assert decoded(cases[f"class-{code}"]) == want, code
        assert decoded(cases[f"valid-{code}"]) is (want != 0), code
    spot = {200: b"OK", 404: b"Not Found", 414: b"URI Too Long",
            500: b"Internal Server Error", 505: b"HTTP Version Not Supported",
            501: b"Not Implemented", 418: b"Unknown"}
    for code, text in spot.items():
        got = decoded(cases[f"reason-{code}"])
        assert bytes(got["data"][: got["length"]]) == text, code


@pytest.mark.parametrize("backend", backends_to_test())
def test_uri_splits(backend):
    vectors = [
        # id, raw, valid, path, query or None
        ("root", b"/", 0, b"/", None),
        ("path", b"/users/42", 0, b"/users/42", None),
        ("query", b"/s?q=1&r=2", 0, b"/s", b"q=1&r=2"),
        ("empty-q", b"/s?", 0, b"/s", b""),
        ("star", b"*", 0, b"*", None),
        ("empty", b"", 1, None, None),
        ("noroot", b"users", 2, None, None),
        ("space", b"/a b", 3, None, None),
        ("ctl", b"/a\x7f", 3, None, None),
        ("absolute", b"http://h/x", 2, None, None),
        ("embedded-scheme", b"/a://evil", 4, None, None),
    ]
    calls = [
        (cid, "split_target", [BYTES(raw), U64(0), U64(len(raw)), U64(len(raw))])
        for cid, raw, _, _, _ in vectors
    ]
    cases = run("src/web/uri.mncs", "web.uri.v1", calls, backend)
    for cid, raw, valid, path, query in vectors:
        got = decoded(cases[cid])
        assert got["valid"] == valid, f"{cid}: {got}"
        if valid == 0:
            uri = got["uri"]
            assert bytes(raw[uri["path_start"]:uri["path_start"] + uri["path_len"]]) == path, cid
            assert uri["has_query"] is (query is not None), cid
            if query is not None:
                assert bytes(raw[uri["query_start"]:uri["query_start"] + uri["query_len"]]) == query, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_header_name_matchers(backend):
    buf = b"Content-LengthX-HostContent-TypeConnectionTransfer-Encoding"
    # CL 0..13, X separator 14, '-' 15, Host 16..19, CT 20..31,
    # Conn 32..41, TE 42..58.
    spans = {"cl": (0, 14), "host": (16, 4), "ct": (20, 12),
             "conn": (32, 10), "te": (42, 17)}
    tags = {"cl": 0, "host": 1, "ct": 2, "conn": 3, "te": 4}
    calls = []
    for name, (off, ln) in spans.items():
        for tag_name, tag in tags.items():
            calls.append((f"{name}-{tag_name}",
                          "name_is", [BYTES(buf), U64(off), U64(ln), U64(len(buf)), U64(tag)]))
    calls.append(("badtag", "name_is",
                  [BYTES(b"Host"), U64(0), U64(4), U64(4), U64(9)]))
    mixed = b"cOnTeNt-LeNgTh"
    calls.append(("mixed", "name_is",
                  [BYTES(mixed), U64(0), U64(14), U64(14), U64(0)]))
    cases = run("src/web/headers.mncs", "web.headers.v1", calls, backend)
    for name in spans:
        for tag_name in tags:
            want = name == tag_name
            assert decoded(cases[f"{name}-{tag_name}"]) is want, f"{name}-{tag_name}"
    assert decoded(cases["badtag"]) is False
    assert decoded(cases["mixed"]) is True


@pytest.mark.parametrize("backend", backends_to_test())
def test_header_name_validity(backend):
    vectors = [
        ("ok", b"X-Custom-1", True),
        ("empty", b"", False),
        ("space", b"Bad Name", False),
        ("colon", b"a:b", False),
        ("ctl", b"a\x01b", False),
    ]
    calls = [
        (cid, "name_valid", [BYTES(raw), U64(0), U64(len(raw)), U64(len(raw))])
        for cid, raw, _ in vectors
    ]
    cases = run("src/web/headers.mncs", "web.headers.v1", calls, backend)
    for cid, _raw, want in vectors:
        assert decoded(cases[cid]) is want, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_header_block_ops(backend):
    from web_exec import synth_header, synth_header_block
    # buf layout: "Host: h1\r\nContent-Length: 5\r\nHOST: h2"
    buf = b"Host: h1\r\nContent-Length: 5\r\nHOST: h2"
    # Host 0..3, value h1 at 6..7; Content-Length 10..23, value 5 at 26;
    # HOST 29..32, value h2 at 35..36.
    block = synth_header_block([
        synth_header(0, 4, 6, 2),
        synth_header(10, 14, 26, 1),
        synth_header(29, 4, 35, 2),
    ])
    calls = [
        ("get-host", "header_get", [block, BYTES(buf), U64(len(buf)), U64(1)]),
        ("get-cl", "header_get", [block, BYTES(buf), U64(len(buf)), U64(0)]),
        ("get-conn", "header_get", [block, BYTES(buf), U64(len(buf)), U64(3)]),
        ("push", "block_push",
         [synth_header_block(), synth_header(0, 4, 6, 2)]),
    ]
    full = synth_header_block([synth_header(0, 1, 2, 1)] * 32)
    calls.append(("push-full", "block_push", [full, synth_header()]))
    cases = run("src/web/headers.mncs", "web.headers.v1", calls, backend)
    host = decoded(cases["get-host"])
    assert host["found"] is True
    assert (host["value_start"], host["value_len"]) == (6, 2)
    cl = decoded(cases["get-cl"])
    assert cl["found"] is True
    assert (cl["value_start"], cl["value_len"]) == (26, 1)
    assert decoded(cases["get-conn"])["found"] is False
    pushed = decoded(cases["push"])
    assert pushed["accepted"] is True
    assert pushed["block"]["count"] == 1
    assert decoded(cases["push-full"])["accepted"] is False
    # content_length_of lives in web.message.v1 (same block shapes).
    msg = run("src/web/message.mncs", "web.message.v1",
              [("cl", "content_length_of", [block, BYTES(buf), U64(len(buf))]),
               ("cl-none", "content_length_of",
                [synth_header_block([synth_header(0, 4, 6, 2)]),
                 BYTES(buf), U64(len(buf))]),
               ("cl-bad", "content_length_of",
                [synth_header_block([synth_header(10, 14, 6, 2)]),
                 BYTES(buf), U64(len(buf))])], backend)
    got = decoded(msg["cl"])
    assert got == {"found": True, "length": 5, "valid": True}, got
    got = decoded(msg["cl-none"])
    assert got == {"found": False, "length": 0, "valid": True}, got
    got = decoded(msg["cl-bad"])
    assert got["found"] is True and got["valid"] is False, got


@pytest.mark.parametrize("backend", backends_to_test())
def test_content_length_digits(backend):
    vectors = [
        ("zero", b"0", True, 0),
        ("small", b"5", True, 5),
        ("mid", b"1024", True, 1024),
        ("max", b"4294967295", True, 4294967295),
        ("over", b"4294967296", False, 0),
        ("empty", b"", False, 0),
        ("alpha", b"12a", False, 0),
        ("space", b" 5", False, 0),
        ("eleven", b"00000000001", False, 0),
        ("leadzero", b"007", True, 7),
    ]
    calls = [
        (cid, "parse_digits", [BYTES(raw), U64(0), U64(len(raw)), U64(len(raw))])
        for cid, raw, _, _ in vectors
    ]
    cases = run("src/web/message.mncs", "web.message.v1", calls, backend)
    for cid, _raw, valid, value in vectors:
        got = decoded(cases[cid])
        assert got["valid"] is valid, f"{cid}: {got}"
        if valid:
            assert got["value"] == value, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_error_codes_and_status_map(backend):
    names = ["None_", "BadMethod", "BadTarget", "BadVersion", "BadStartLine",
             "BadHeader", "BadName", "BadSeparator", "BadContentLength",
             "TooLongStartLine", "TooLongHeader", "TooManyHeaders",
             "HeadTooLarge", "BodyTooLarge", "BadStatus", "Overflow",
             "UnsupportedTransfer"]
    want_status = [0, 400, 400, 505, 400, 400, 400, 400, 400, 414, 400,
                   431, 431, 413, 500, 500, 501]
    calls = []
    for disc, name in enumerate(names):
        fin = FIN("web.error.v1", "Error", name, disc)
        calls.append((f"code-{name}", "code_of", [fin]))
        calls.append((f"limit-{name}", "is_limit", [fin]))
    for code in range(18):
        calls.append((f"of-{code}", "error_of", [U64(code)]))
        calls.append((f"st-{code}", "status_for_code", [U64(code)]))
    cases = run("src/web/error.mncs", "web.error.v1", calls, backend)
    for disc, name in enumerate(names):
        assert decoded(cases[f"code-{name}"]) == disc, name
        assert decoded(cases[f"limit-{name}"]) is (9 <= disc <= 13), name
    for code in range(18):
        want_disc = code if code <= 16 else 0
        assert decoded(cases[f"of-{code}"])["discriminant"] == want_disc, code
        want_st = want_status[code] if code <= 16 else 0
        assert decoded(cases[f"st-{code}"]) == want_st, code


@pytest.mark.parametrize("backend", backends_to_test())
def test_limits_defaults_and_clamp(backend):
    calls = [
        ("default", "default_limits", []),
        ("tiny", "tiny_limits", []),
        ("clamp", "limits_make", [U64(5000), U64(0), U64(99), U64(10), U64(7)]),
        ("static-wire", "static_wire", []),
        ("static-headers", "static_headers", []),
    ]
    cases = run("src/web/limits.mncs", "web.limits.v1", calls, backend)
    default = decoded(cases["default"])
    assert default == {"max_start_line": 512, "max_header_line": 512,
                       "max_headers": 32, "max_head_bytes": 1024,
                       "max_body_bytes": 1024}, default
    tiny = decoded(cases["tiny"])
    assert tiny == {"max_start_line": 16, "max_header_line": 16,
                    "max_headers": 2, "max_head_bytes": 32,
                    "max_body_bytes": 8}, tiny
    clamped = decoded(cases["clamp"])
    assert clamped == {"max_start_line": 1024, "max_header_line": 1,
                       "max_headers": 32, "max_head_bytes": 10,
                       "max_body_bytes": 7}, clamped
    assert decoded(cases["static-wire"]) == 1024
    assert decoded(cases["static-headers"]) == 32
