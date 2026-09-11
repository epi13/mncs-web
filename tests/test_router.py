"""Router tests: default-table matching plus synthesized custom tables
(priority order, ANY-method wildcard, param rules)."""

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
    require_returned,
    slice_span,
    vval,
)

SOURCE = "src/web/router.mncs"
MOD = "web.router.v1"


def run(calls, backend):
    return check_cases(call_many(SOURCE, MOD, calls, backend))


def match(buf, method, path):
    off = buf.index(path)
    return ["match_default", [BYTES(buf), U64(len(buf)), U64(method), U64(off), U64(len(path))]]


def pat(raw):
    data = bytes(raw)
    assert len(data) <= 32
    return {"sequence": {"values": [{"byte": {"value": b}} for b in data] + [{"byte": {"value": 0}}] * (32 - len(data))}}


def route(method, pattern, has_param, prefix_len, handler):
    return REC("web.router.v1", "Route", [
        ("method", U64(method)),
        ("pattern", pat(pattern)),
        ("pattern_len", U64(len(pattern))),
        ("has_param", {"boolean": {"value": has_param}}),
        ("prefix_len", U64(prefix_len)),
        ("handler", U64(handler)),
    ])


@pytest.mark.parametrize("backend", backends_to_test())
def test_default_table(backend):
    vectors = [
        # id, buf, method, path, found, handler, param, path_exists
        ("health", b"GET /health", 0, b"/health", True, 0, None, True),
        ("users", b"GET /users", 0, b"/users", True, 1, None, True),
        ("user", b"GET /users/42", 0, b"/users/42", True, 2, b"42", True),
        ("items", b"POST /items", 1, b"/items", True, 3, None, True),
        ("version", b"GET /version", 0, b"/version", True, 4, None, True),
        ("miss", b"GET /nope", 0, b"/nope", False, 0, None, False),
        ("method-miss", b"POST /health", 1, b"/health", False, 0, None, True),
        ("del-user", b"DELETE /users/1", 3, b"/users/1", False, 0, None, True),
        ("empty-param", b"GET /users/", 0, b"/users/", False, 0, None, False),
        ("slash-param", b"GET /users/a/b", 0, b"/users/a/b", False, 0, None, False),
        ("prefix-attack", b"GET /users2", 0, b"/users2", False, 0, None, False),
        ("case", b"GET /HEALTH", 0, b"/HEALTH", False, 0, None, False),
        ("post-users", b"POST /users", 1, b"/users", False, 0, None, True),
    ]
    calls = [(cid, *match(buf, method, path)) for cid, buf, method, path, *_ in vectors]
    cases = run(calls, backend)
    for cid, buf, _method, _path, found, handler, param, exists in vectors:
        got = vval(require_returned(cases[cid], "router"))
        assert got["found"] is found, f"{cid}: {got}"
        assert got["path_exists"] is exists, f"{cid}: exists {got}"
        if found:
            assert got["handler"] == handler, cid
            assert got["has_param"] is (param is not None), cid
            if param is not None:
                assert slice_span(buf, got["param_start"], got["param_len"]) == param, cid


@pytest.mark.parametrize("backend", backends_to_test())
def test_custom_table_priority_and_wildcard(backend):
    # Table: exact GET /a -> 7, ANY /a -> 8, GET /b/ param -> 9.
    # Priority is table order; ANY matches every method.
    buf = b"/a/b/c"
    # path spans: "/a" at 0..2, "/b/" hmm build per-case buffers instead.
    routes = [
        route(0, b"/a", False, 2, 7),
        route(10, b"/a", False, 2, 8),
        route(0, b"/b/", True, 3, 9),
    ]
    blanks = []
    table = REC("web.router.v1", "RouteTable", [
        ("routes", {"sequence": {"values": routes + [blank_route() for _ in range(13)]}}),
        ("count", U64(3)),
    ])
    vectors = [
        ("exact-first", b"/a", 0, True, 7, None),
        ("any-fallback", b"/a", 1, True, 8, None),
        ("param", b"/b/xy", 0, True, 9, b"xy"),
        ("param-method", b"/b/xy", 1, False, 0, None),
        ("miss", b"/c", 0, False, 0, None),
    ]
    calls = []
    for cid, path, method, _found, _handler, _param in vectors:
        calls.append((cid, "route_match",
                      [table, BYTES(path), U64(len(path)), U64(method), U64(0), U64(len(path))]))
    cases = run(calls, backend)
    for cid, path, _method, found, handler, param in vectors:
        got = vval(require_returned(cases[cid], "router"))
        assert got["found"] is found, f"{cid}: {got}"
        if found:
            assert got["handler"] == handler, cid
            if param is not None:
                assert slice_span(path, got["param_start"], got["param_len"]) == param, cid


def blank_route():
    return REC("web.router.v1", "Route", [
        ("method", U64(10)),
        ("pattern", pat(b"")),
        ("pattern_len", U64(0)),
        ("has_param", {"boolean": {"value": False}}),
        ("prefix_len", U64(0)),
        ("handler", U64(0)),
    ])
