# Tests

Every assertion executes real `mncs-language` programs through the
reference CLI (`experiment run`). Python only transports byte views
across the process boundary and decodes results; it never reimplements
HTTP semantics. The one deliberate exception: hand-written expected
wire bytes (RFC framing), which are an independent oracle by
construction.

## Layout

- `web_exec.py` — harness: CLI transport, value constructors (`BYTES`,
  `U64`, `U16`, `B`), result decoders (`vval`, `head_spans`,
  `slice_span`), identity harvesting and record/finite synthesis
  (`ensure_identities`, `REC`, `FIN`, `synth_*`), backend selection,
  feed-budget scaling (`feed_budget`).
- `test_harness.py` — harness unit tests, no CLI: `REC` canonical
  field order (WEB-P-011) at every nesting level.
- `test_types.py` — leaf units: method, version, status, URI, header
  matchers/block ops, Content-Length digits, errors, limits.
- `test_parser.py` — valid/incomplete/malformed/limit/response/cross
  batteries plus pipelining prefix behavior.
- `test_fragmentation.py` — prefix incompleteness, every-split
  reassembly, chunk-size convergence (`feed_pattern`), staged
  overflow, `Parser` record paths (settle/idempotence via synthesized
  states).
- `test_roundtrip.py` — in-language round-trip laws (request and
  response) plus the chunked-framing negative.
- `test_router.py` — default-table matching and synthesized custom
  tables (priority, ANY-method, param rules).
- `test_encoder.py` — byte-exact response wire output.
- `test_query.py` — pair lookup, first-wins, pct validation, and a
  parser→query span composition.
- `test_app.py` — `serve_once` model verdicts and `serve_bytes` wire
  output for every demo route and error mapping.
- `test_transport.py` — pipe write/read/backpressure/accounting with
  synthesized states, a true record-threading chain, and a
  request→pipe→serve→pipe→response loopback.

Batteries are generated in-process (no checked-in corpora): the
fragmentation matrices are too large to check in sanely, and one
mechanism (`call_many` batching) covers everything. Each test function
makes exactly one CLI invocation per backend, so the suite stays
linear in files, not cases. Measured wall time on
`mncs-research-bytecode` (this host): leaf files ~1 min, parser +
encoder + router + types + query 27 tests ~20 min, round-trip laws
~9 min, fragmentation ~30 min, app + transport + examples + smoke
~14 min. Single invocations range from ~5 s (leaf modules) to ~10 min
(2M-step chunked feeds); the harness CLI timeout is 600 s. Step
budgets per entry point are recorded in `benchmarks/README.md`.

## Running

```bash
# default: the two fast backends (no external toolchain)
python3 -m pytest tests/ -q
# full matrix where toolchains exist
MNCS_BACKENDS=mncs-research-bytecode,mncs-portable-wasm-mvp,mncs-c11,mncs-llvm-ir,mncs-cranelift \
  python3 -m pytest tests/ -q
# one file / one backend while iterating
MNCS_BACKENDS=mncs-research-bytecode python3 -m pytest tests/test_parser.py -q
```

`MNCS_BIN` and `MNCS_LANG_LIB` override the compiler binary and the
language library path. `tests/target/identities.json` caches harvested
type identities keyed by source hash (regenerated automatically).

## Backend chunk-coverage (WEB-P-012)

`test_fragmentation.py` runs the full 1/5/64-byte chunk battery on
bytecode. Other backends run the within-ceiling subset; excluded sizes
print a `SKIP ... (WEB-P-012)` line per test (visible with `-s`) and
are tabulated here — reported, never silent:

| message | size 1 (live) | size 5 (live) | size 64 (live) |
|---|---|---|---|
| min 37 B | bytecode only (37) | bytecode + wasm (8) | all (1) |
| post 57 B | bytecode only (57) | bytecode + wasm (12) | all (1) |
| multi 96 B | bytecode only (96) | bytecode only (20) | all (2) |

Ceilings (live chunks, verified by execution): bytecode unlimited;
wasm 12 (12 pass / 13 trap); c11, llvm-ir, cranelift 2 (1-2 pass;
c11 fails at 10; llvm/cranelift unprobed above 2). Unknown backends
fail closed in `allowed_chunk_sizes`.

## Backend policy

PASS or honest-UNKNOWN both count as green for obligations, but every
behavioral case must `returned` with the exact expected value on every
backend under test. A backend that cannot run here (missing toolchain)
is reported, not silently skipped: narrowing `MNCS_BACKENDS` is the
explicit mechanism.
