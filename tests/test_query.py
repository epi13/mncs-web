"""Query-codec tests: pair lookup, first-wins, edge values, pct validation,
plus a parser->query span composition check."""

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

SOURCE = "src/web/query.mncs"
MOD = "web.query.v1"


def key(s):
    return BYTES(s), U64(len(s))


def run(calls, backend):
    return check_cases(call_many(SOURCE, MOD, calls, backend))


def lookup(case):
    return vval(require_returned(case, "query"))


@pytest.mark.parametrize("backend", backends_to_test())
def test_query_value(backend):
    buf = b"a=1&b=2&flag&e=&a=second&x=y=z"
    vectors = [
        ("b", (True, b"2")),
        ("a", (True, b"1")),
        ("flag", (True, b"")),
        ("e", (True, b"")),
        ("x", (True, b"y=z")),
        ("missing", (False, b"")),
        ("a1", (False, b"")),
        ("ab", (False, b"")),
    ]
    calls = []
    for key_name, _ in vectors:
        kb, kl = key(key_name.encode())
        calls.append((f"q-{key_name}", "query_value",
                      [BYTES(buf), U64(len(buf)), U64(0), U64(len(buf)), kb, kl]))
    calls.append(("q-empty", "query_value",
                  [BYTES(b""), U64(0), U64(0), U64(0), BYTES(b"a"), U64(1)]))
    kb, kl = key(b"")
    calls.append(("q-emptykey", "query_value",
                  [BYTES(buf), U64(len(buf)), U64(0), U64(len(buf)), kb, kl]))
    cases = run(calls, backend)
    for key_name, (found, value) in vectors:
        got = lookup(cases[f"q-{key_name}"])
        assert got["found"] is found, key_name
        if found:
            assert slice_span(buf, got["value_start"], got["value_len"]) == value, key_name
    assert lookup(cases["q-empty"])["found"] is False
    assert lookup(cases["q-emptykey"])["found"] is False


@pytest.mark.parametrize("backend", backends_to_test())
def test_query_window_and_pct(backend):
    buf = b"zzza=%20&b=%2G"
    calls = [
        ("pct-ok", "pairs_valid", [BYTES(buf), U64(len(buf)), U64(3), U64(6)]),
        ("pct-bad", "pairs_valid", [BYTES(buf), U64(len(buf)), U64(9), U64(5)]),
        ("pct-trunc", "pairs_valid", [BYTES(b"a=%"), U64(4), U64(0), U64(4)]),
        ("pct-short", "pairs_valid", [BYTES(b"a=%2"), U64(4), U64(0), U64(4)]),
        ("pct-empty", "pairs_valid", [BYTES(b""), U64(0), U64(0), U64(0)]),
        ("pct-plain", "pairs_valid", [BYTES(b"a+b=c"), U64(5), U64(0), U64(5)]),
    ]
    cases = run(calls, backend)
    assert lookup(cases["pct-ok"]) is True
    assert lookup(cases["pct-bad"]) is False
    assert lookup(cases["pct-trunc"]) is False
    assert lookup(cases["pct-short"]) is False
    assert lookup(cases["pct-empty"]) is True
    assert lookup(cases["pct-plain"]) is True


@pytest.mark.parametrize("backend", backends_to_test())
def test_query_over_parsed_span(backend):
    # Compose across modules in Python: parse the request, then look up a
    # key inside the parsed query span of the same buffer.
    raw = b"GET /s?q=MNCS&r=2 HTTP/1.1\r\n\r\n"
    parse_out = check_cases(call_many(
        "src/web/parser.mncs", "web.parser.v1",
        [("p", "parse_default", [BYTES(raw), U64(len(raw))])], backend))
    head = vval(require_returned(parse_out["p"], "parse"))["head"]
    target = head["target"]
    assert target["has_query"] is True
    krb, krl = key(b"r")
    kqb, kql = key(b"q")
    query_out = run([
        ("r", "query_value",
         [BYTES(raw), U64(len(raw)),
          U64(target["query_start"]), U64(target["query_len"]), krb, krl]),
        ("q", "query_value",
         [BYTES(raw), U64(len(raw)),
          U64(target["query_start"]), U64(target["query_len"]), kqb, kql]),
    ], backend)
    got = lookup(query_out["r"])
    assert got["found"] is True
    assert slice_span(raw, got["value_start"], got["value_len"]) == b"2"
    got = lookup(query_out["q"])
    assert slice_span(raw, got["value_start"], got["value_len"]) == b"MNCS"
