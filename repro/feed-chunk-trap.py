"""Reproducer for WEB-P-012: native backends trap past small staging counts.

Runs `feed_pattern` twice on the same backend: a 5-live-chunk control
(5 B message, chunk size 1) and a 13-live-chunk trigger (37 B message,
chunk size 3). Expected: both `returned`. Actual: the control returns
everywhere; the trigger returns only on mncs-research-bytecode and
dies on every native backend (wasm: out-of-bounds store trap;
cranelift: arena exhaustion; c11/llvm: bare runtime_failure).

Usage (from the mncs-web repo root):
    python3 repro/feed-chunk-trap.py [backend]
Default backend: mncs-portable-wasm-mvp.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from web_exec import BYTES, U64, call_many  # noqa: E402

DEF = [U64(512), U64(512), U64(32), U64(1024), U64(1024)]
CONTROL = b"GET /"  # 5 B, chunk 1 -> 5 live chunks
TRIGGER = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"  # 37 B, chunk 3 -> 13 live


def main(backend):
    out = call_many("src/web/parser.mncs", "web.parser.v1", [
        ("control-5-live", "feed_pattern",
         [BYTES(CONTROL), U64(len(CONTROL)), U64(1)] + DEF, 4000000),
        ("trigger-13-live", "feed_pattern",
         [BYTES(TRIGGER), U64(len(TRIGGER)), U64(3)] + DEF, 8000000),
    ], backend)
    for cid in ("control-5-live", "trigger-13-live"):
        case = out[cid]
        print(f"{cid}: status={case.get('status')}"
              f" failure={case.get('failure_reason')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mncs-portable-wasm-mvp")
