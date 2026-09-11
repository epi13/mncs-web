"""Reproducer for WEB-P-011: record corpus field order.

The same `header_get` call is issued twice on the same backend: once
with record fields in MNCS source declaration order, once in canonical
(alphabetical) order. Expected: both return the found header.
Actual (pre-contract-fix): declaration order is `returned` on
mncs-research-bytecode but `invalid_request` on
mncs-portable-wasm-mvp; canonical order is `returned` on both.

Usage (from the mncs-web repo root):
    python3 repro/record-field-order.py [backend]
Default backend: mncs-portable-wasm-mvp.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from web_exec import BYTES, U64, call_many, ensure_identities  # noqa: E402

BUF = b"Host: h1\r\nContent-Length: 5\r\nHOST: h2"


def rec(fields):
    tid = ensure_identities()["web.headers.v1::HeaderBlock"]
    return {"record": {"type_identity": tid, "name": "HeaderBlock", "fields": fields}}


def hdr(pairs):
    tid = ensure_identities()["web.headers.v1::Header"]
    return {"record": {"type_identity": tid, "name": "Header", "fields": pairs}}


def blank():
    return hdr([[k, U64(0)] for k in ("name_len", "name_start", "value_len", "value_start")])


def main(backend):
    one = hdr([["name_len", U64(4)], ["name_start", U64(0)],
               ["value_len", U64(2)], ["value_start", U64(6)]])
    seq = {"sequence": {"values": [one] + [blank() for _ in range(31)]}}
    # Declaration order: headers, then count. Canonical order: count,
    # then headers (matches the type_identity spelling).
    decl = rec([["headers", seq], ["count", U64(1)]])
    canon = rec([["count", U64(1)], ["headers", seq]])
    calls = [
        ("decl-order", "header_get", [decl, BYTES(BUF), U64(len(BUF)), U64(1)]),
        ("canon-order", "header_get", [canon, BYTES(BUF), U64(len(BUF)), U64(1)]),
    ]
    out = call_many("src/web/headers.mncs", "web.headers.v1", calls, backend)
    for cid in ("decl-order", "canon-order"):
        case = out[cid]
        print(f"{cid}: status={case.get('status')}"
              f" failure={case.get('failure_reason')}")
        if case.get("status") == "returned":
            print(f"  returned={case['returned']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mncs-portable-wasm-mvp")
