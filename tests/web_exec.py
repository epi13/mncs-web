"""Shared MNCS execution helpers for mncs-web tests.

Every protocol byte asserted by this suite is produced by executing
mncs-language programs (src/web/*.mncs) through the reference compiler
CLI. This module only transports values across the process boundary and
parses results; it never reimplements HTTP semantics. The one exception
is Python's own HTTP framing, used strictly as an INDEPENDENT oracle in
a small number of cross-check tests (mncs-web must never depend on it
for canonical bytes).
"""

import json
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
CORPORA_DIR = os.path.join(REPO_ROOT, "tests", "corpora")

MNCS_BIN = os.environ.get(
    "MNCS_BIN",
    "/home/epi13/Documents/Projects/mncs-language/target/debug/mncs",
)
MNCS_LANG_LIB = os.environ.get(
    "MNCS_LANG_LIB", "/home/epi13/Documents/Projects/mncs-language/library"
)

BACKENDS = [
    "mncs-research-bytecode",
    "mncs-portable-wasm-mvp",
    "mncs-c11",
    "mncs-llvm-ir",
    "mncs-cranelift",
]

# Backends that run without a C toolchain / external runtime on this host.
FAST_BACKENDS = ["mncs-research-bytecode", "mncs-portable-wasm-mvp"]

STEP_BUDGET = 200000
RUN_TIMEOUT_S = 600

# The wasm backend charges more steps per staging operation than the
# bytecode interpreter (min-chunk-1 exhausts the 1M bytecode-sized
# budget). Feed-heavy tests scale their budgets through here; one-shot
# parses need no scaling (verified at 200k on wasm).
WASM_FEED_SCALE = 4


def feed_budget(base, backend):
    if backend == "mncs-portable-wasm-mvp":
        return base * WASM_FEED_SCALE
    return base


class WebHarnessError(Exception):
    pass


def backends_to_test():
    raw = os.environ.get("MNCS_BACKENDS", "")
    if raw.strip():
        wanted = [b.strip() for b in raw.split(",") if b.strip()]
        unknown = [b for b in wanted if b not in BACKENDS]
        if unknown:
            raise WebHarnessError(f"unknown backends in MNCS_BACKENDS: {unknown}")
        return wanted
    return list(FAST_BACKENDS)


def library_path():
    return MNCS_LANG_LIB + ":" + SRC_DIR


def I(value, bits=64, signed=False):
    return {"integer": {"value": value, "type": {"bits": bits, "signed": signed}}}


def U64(value):
    return I(value, 64, False)


def U16(value):
    return I(value, 16, False)


def B(value):
    return {"boolean": {"value": bool(value)}}


def BY(value):
    return {"byte": {"value": value}}


def BYTES(data):
    return {"sequence": {"values": [BY(b) for b in bytes(data)]}}


def req(module, function, args, budget=STEP_BUDGET):
    return {
        "schema_version": "0.1",
        "target": {"module": module, "function": function},
        "arguments": args,
        "step_budget": budget,
    }


def run_corpus(source, corpus, backend, corpus_path=None):
    """Run `experiment run` and return (returncode, result_dict, stderr)."""
    src = source if os.path.isabs(source) else os.path.join(REPO_ROOT, source)
    if corpus_path is not None:
        cpath = (
            corpus_path
            if os.path.isabs(corpus_path)
            else os.path.join(REPO_ROOT, corpus_path)
        )
        tmp = None
    else:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(
            suffix=".json", prefix="mncs-web-case-", delete=False
        )
        tmp.write(json.dumps(corpus).encode())
        tmp.close()
        cpath = tmp.name
    try:
        cmd = [MNCS_BIN, "experiment", "run", src, "--backend", backend,
               "--corpus", cpath]
        env = dict(os.environ)
        env["MNCS_LIBRARY_PATH"] = library_path()
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env
        )
        try:
            result = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            result = None
        return proc.returncode, result, proc.stderr
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def call_many(source, module, calls, backend):
    """Batch N calls into one CLI invocation.

    Each call is (case_id, function, args[, budget]); budget defaults to
    STEP_BUDGET. Size budgets to the entry point: leaf scanners run at
    50k, one-shot parses at 200k, serve compositions at 200-300k,
    response round-trips and split feeds at 500k, request round-trips
    at 1M, and chunked feeds at 500k-2M by chunk size and message
    length (see benchmarks/README.md).
    """
    cases = []
    for call in calls:
        if len(call) == 4:
            cid, fn, args, budget = call
        else:
            cid, fn, args = call
            budget = STEP_BUDGET
        cases.append({"id": cid, "request": req(module, fn, args, budget)})
    corpus = {
        "schema_version": "0.1",
        "name": "mncs-web-batch",
        "cases": cases,
    }
    code, result, stderr = run_corpus(source, corpus, backend)
    if result is None or "cases" not in result:
        raise WebHarnessError(
            f"mncs run produced no result JSON (exit={code}): {stderr[-2000:]}"
        )
    out = {c["case_id"]: c for c in result["cases"]}
    missing = [call[0] for call in calls if call[0] not in out]
    if missing:
        raise WebHarnessError(f"mncs run dropped cases: {missing}")
    return out


def require_returned(case, what):
    if case.get("status") != "returned" or not case.get("returned"):
        raise WebHarnessError(
            f"{what}: expected a returned value, got status="
            f"{case.get('status')} failure={case.get('failure_reason')}"
        )
    if len(case["returned"]) != 1:
        raise WebHarnessError(
            f"{what}: expected exactly one returned value, got "
            f"{len(case['returned'])}"
        )
    return case["returned"][0]


def as_int(value):
    return int(value["integer"]["value"])


def as_bool(value):
    return bool(value["boolean"]["value"])


def as_bytes(value):
    """Convert a `sequence of byte` result value to Python bytes."""
    return bytes(item["byte"]["value"] for item in value["sequence"]["values"])


def as_record(value):
    """Convert a record result value to {field: raw_value}."""
    fields = value["record"]["fields"]
    return {name: val for name, val in fields}


def as_finite(value):
    """Convert a finite/enum result value to (discriminant, {field: raw})."""
    fin = value["finite"]
    payload = {name: val for name, val in fin.get("payload", [])}
    return int(fin["discriminant"]), payload


def vval(value):
    """Decode any MNCS value JSON to plain Python (ints/bools/bytes/dicts)."""
    if "integer" in value:
        return int(value["integer"]["value"])
    if "boolean" in value:
        return bool(value["boolean"]["value"])
    if "byte" in value:
        return int(value["byte"]["value"])
    if "record" in value:
        return {k: vval(x) for k, x in value["record"]["fields"]}
    if "sequence" in value:
        items = value["sequence"]["values"]
        if items and "byte" in items[0]:
            return bytes(x["byte"]["value"] for x in items)
        return [vval(x) for x in items]
    if "finite" in value:
        fin = value["finite"]
        return {
            "discriminant": int(fin["discriminant"]),
            "payload": {k: vval(x) for k, x in fin.get("payload", [])},
        }
    raise WebHarnessError(f"unknown value shape: {list(value)}")


def head_spans(head):
    """Return the header spans of a decoded RequestHead/ResponseHead dict."""
    headers = head["headers"]["headers"][: head["headers"]["count"]]
    return [
        (h["name_start"], h["name_len"], h["value_start"], h["value_len"])
        for h in headers
    ]


def slice_span(buf, start, length):
    return bytes(buf[start : start + length])


def rec_field(record_value, name):
    """Fetch a named field from a raw record corpus value (no decoding)."""
    for key, value in record_value["record"]["fields"]:
        if key == name:
            return value
    raise WebHarnessError(f"record has no field {name!r}")


def _zero_bytes(n):
    return {"sequence": {"values": [{"byte": {"value": 0}} for _ in range(n)]}}


def synth_header(name_start=0, name_len=0, value_start=0, value_len=0):
    return REC("web.headers.v1", "Header", [
        ("name_start", U64(name_start)),
        ("name_len", U64(name_len)),
        ("value_start", U64(value_start)),
        ("value_len", U64(value_len)),
    ])


def synth_header_block(headers=()):
    blanks = [synth_header() for _ in range(32 - len(headers))]
    return REC("web.headers.v1", "HeaderBlock", [
        ("headers", {"sequence": {"values": list(headers) + blanks}}),
        ("count", U64(len(headers))),
    ])


def synth_uri(path_start=0, path_len=0, query_start=0, query_len=0, has_query=False):
    return REC("web.uri.v1", "Uri", [
        ("path_start", U64(path_start)),
        ("path_len", U64(path_len)),
        ("query_start", U64(query_start)),
        ("query_len", U64(query_len)),
        ("has_query", B(has_query)),
    ])


def synth_request_head(**over):
    fields = {
        "method": U64(9),
        "ext_start": U64(0),
        "ext_len": U64(0),
        "target": synth_uri(),
        "version": U64(1),
        "headers": synth_header_block(),
        "content_length": U64(0),
        "has_content_length": B(False),
        "body_start": U64(0),
        "body_len": U64(0),
        "head_len": U64(0),
    }
    fields.update(over)
    order = ["method", "ext_start", "ext_len", "target", "version", "headers",
             "content_length", "has_content_length", "body_start", "body_len",
             "head_len"]
    return REC("web.message.v1", "RequestHead", [(k, fields[k]) for k in order])


def synth_response_head(**over):
    fields = {
        "version": U64(1),
        "status": {"integer": {"value": 200, "type": {"bits": 16, "signed": False}}},
        "reason_start": U64(0),
        "reason_len": U64(0),
        "headers": synth_header_block(),
        "body_start": U64(0),
        "body_len": U64(0),
    }
    fields.update(over)
    order = ["version", "status", "reason_start", "reason_len", "headers",
             "body_start", "body_len"]
    return REC("web.message.v1", "ResponseHead", [(k, fields[k]) for k in order])


def synth_parseout(kind=1, error=0, consumed=0, is_response=False,
                   head=None, response=None):
    return REC("web.parser.v1", "ParseOut", [
        ("kind", U64(kind)),
        ("error", U64(error)),
        ("consumed", U64(consumed)),
        ("is_response", B(is_response)),
        ("head", head if head is not None else synth_request_head()),
        ("response", response if response is not None else synth_response_head()),
    ])


def synth_parser(staged_len=0, out=None, settled=False, staged=None):
    return REC("web.parser.v1", "Parser", [
        ("staged", staged if staged is not None else _zero_bytes(1024)),
        ("staged_len", U64(staged_len)),
        ("out", out if out is not None else synth_parseout()),
        ("settled", B(settled)),
    ])


def check_cases(out, expect_returned=True):
    """Assert every case in a call_many result dict returned successfully."""
    assert out, "experiment produced no cases"
    for cid, case in out.items():
        assert case.get("status") == "returned", (
            f"{cid}: status={case.get('status')} "
            f"failure={case.get('failure_reason')}"
        )
        if expect_returned:
            assert case.get("returned"), f"{cid}: empty return"
    return out


def _src_hash():
    import hashlib

    h = hashlib.sha256()
    for name in sorted(os.listdir(os.path.join(SRC_DIR, "web"))):
        if name.endswith(".mncs"):
            with open(os.path.join(SRC_DIR, "web", name), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _walk_identities(value, table):
    if isinstance(value, dict):
        if "record" in value:
            rec = value["record"]
            tid = rec.get("type_identity", "")
            name = rec.get("name", "")
            mod = ""
            if "::" in tid:
                mod = tid.split("::")[0].split("record-type:")[-1]
            if name and tid and (mod, name) not in table:
                table[f"{mod}::{name}"] = tid
            for _, field in rec.get("fields", []):
                _walk_identities(field, table)
        elif "sequence" in value:
            for item in value["sequence"].get("values", []):
                _walk_identities(item, table)
        elif "finite" in value:
            fin = value["finite"]
            tid = fin.get("type_identity", "")
            name = ""
            if "::" in tid:
                name = tid.split("::")[-1]
                mod = tid.split("::")[0].split("finite-type:")[-1]
                key = f"{mod}::{name}"
                if key not in table:
                    table[key] = tid
                variants = table.setdefault(f"{key}::variants", {})
                disc = int(fin["discriminant"])
                variants[disc] = fin.get("variant_identity", "")
            for _, field in fin.get("payload", []):
                _walk_identities(field, table)


def ensure_identities():
    """Harvest record/finite type identities once per source tree.

    Record-typed corpus arguments require exact `type_identity` strings.
    This runs a small bootstrap battery (fast modules plus one parser
    run, bytecode backend only), walks every returned value, and caches
    the identity table under tests/target keyed by source hash.
    """
    target_dir = os.path.join(REPO_ROOT, "tests", "target")
    os.makedirs(target_dir, exist_ok=True)
    cache_path = os.path.join(target_dir, "identities.json")
    digest = _src_hash()
    if os.path.exists(cache_path):
        try:
            import json as _json

            cached = _json.load(open(cache_path))
            if cached.get("src_hash") == digest:
                return cached["identities"]
        except (OSError, ValueError, KeyError):
            pass
    min_get = b"GET / HTTP/1.1\r\nH: v\r\n\r\n"
    batches = [
        ("src/web/transport.mncs", "web.transport.v1", [("b_pipe", "pipe_new", [])]),
        ("src/web/router.mncs", "web.router.v1", [("b_table", "empty_table", [])]),
        ("src/web/error.mncs", "web.error.v1", [("b_err", "error_of", [U64(1)])]),
        ("src/web/method.mncs", "web.method.v1", [
            ("b_meth", "parse", [BYTES(b"GET"), U64(0), U64(3), U64(3)]),
        ]),
        ("src/web/parser.mncs", "web.parser.v1", [
            ("b_parser", "parser_new", []),
            ("b_parse", "parse_default", [BYTES(min_get), U64(len(min_get))]),
        ]),
    ]
    table = {}
    for source, module, calls in batches:
        out = call_many(source, module, calls, "mncs-research-bytecode")
        for cid, case in out.items():
            returned = require_returned(case, f"bootstrap {cid}")
            _walk_identities(returned, table)
    import json as _json

    _json.dump({"src_hash": digest, "identities": table}, open(cache_path, "w"))
    return table


def FIN(module, type_name, variant, discriminant, payload=()):
    """Synthesize a finite (enum) corpus argument."""
    table = ensure_identities()
    key = f"{module}::{type_name}"
    tid = table[key]
    variants = table.get(f"{key}::variants", {})
    vid = variants.get(discriminant)
    if vid is None:
        vid = f"mncs:0.2:finite-variant:{module}::{type_name}::{variant}"
    return {
        "finite": {
            "type_identity": tid,
            "variant_identity": vid,
            "discriminant": discriminant,
            "payload": [[k, v] for k, v in payload],
        }
    }


def REC(module, type_name, fields):
    """Synthesize a record corpus argument.

    `fields` is a list of (name, value) pairs in any order; they are
    emitted in canonical (alphabetical) order, which is the order the
    language-owned value contract checks on compiled backends. The
    bytecode interpreter accepts any order, but wasm rejects
    declaration order with invalid_request, so canonical order is
    required for cross-backend corpora (see WEB-P-011). Nested
    records/sequences/finites are plain values (use REC/FIN or
    BYTES/U64/B helpers to build them); nested RECs are sorted
    recursively by construction.
    """
    table = ensure_identities()
    tid = table[f"{module}::{type_name}"]
    return {
        "record": {
            "type_identity": tid,
            "name": type_name,
            "fields": [[k, v] for k, v in sorted(fields, key=lambda kv: kv[0])],
        }
    }


def source_study(path):
    """Run source-study on a repo-relative path; return parsed JSON."""
    full = path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)
    env = dict(os.environ)
    env["MNCS_LIBRARY_PATH"] = library_path()
    proc = subprocess.run(
        [MNCS_BIN, "source-study", full],
        capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env,
    )
    return json.loads(proc.stdout)
