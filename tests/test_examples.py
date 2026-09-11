"""Executed examples: the example modules run on every backend and must
agree with the application suite (examples are verified, not prose)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import (
    backends_to_test,
    call_many,
    check_cases,
    require_returned,
    vval,
)


@pytest.mark.parametrize("backend", backends_to_test())
def test_hello_example(backend):
    calls = [
        ("health-status", "entry_health_status", []),
        ("health-body", "entry_health_body_len", []),
        ("user-status", "entry_user_status", []),
        ("missing-status", "entry_missing_status", []),
        ("wire-len", "entry_health_wire_len", []),
    ]
    cases = check_cases(call_many("examples/hello.mncs", "ex.hello.v1", calls, backend))
    assert vval(require_returned(cases["health-status"], "ex")) == 200
    assert vval(require_returned(cases["health-body"], "ex")) == 15
    assert vval(require_returned(cases["user-status"], "ex")) == 200
    assert vval(require_returned(cases["missing-status"], "ex")) == 404
    wire_len = vval(require_returned(cases["wire-len"], "ex"))
    assert wire_len == len(
        b"HTTP/1.1 200 OK\r\nContent-Length: 15\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b'{"status":"ok"}'
    ), wire_len
