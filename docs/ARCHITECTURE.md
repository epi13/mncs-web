# Architecture

`mncs-web` sits above MNCS byte/sequence primitives and below user
applications. It is a pressure project first: every layer must be
honestly executable today, with missing capabilities recorded as
language pressure rather than hidden behind foreign substitutes.

## Status

Foundation vertical slice implemented (all in `mncs-language`,
Profile 0.13, executed on all compilable backends):

```text
typed protocol structures (method/status/version/uri/headers/limits/errors)
        ↓
incremental byte parser as an explicit state machine (requests + responses)
        ↓
HTTP encoder (requests + responses)
        ↓
in-language round-trip laws (parse → encode → parse)
        ↓
memory-backed transport pipes
        ↓
deterministic router + demo handlers (request → handler → response)
        ↓
pytest suite driving real MNCS executions (no reimplementation oracles)
```

## Layers and modules

```text
src/web/
  error.mncs      failure vocabulary (enum + stable u64 codes + status map)
  limits.mncs     runtime resource bounds clamped to static capacities
  method.mncs     Method enum (9 known + EXT escape hatch), tchar validation
  version.mncs    HTTP/1.0/1.1 tokens (exact parse; resumption lives in parser)
  status.mncs     u16 codes, classes, standard reason table (32-byte slot)
  uri.mncs        origin-form + asterisk-form target spans, scheme rejection
  headers.mncs    HeaderBlock (32), case-insensitive known-name matchers
  message.mncs    RequestHead/ResponseHead, decimal + Content-Length accounting
  parser.mncs     one-shot scan, Parser staging, feed_flat, feed_pattern
  encode.mncs     request/response serializers with truncation reporting
  roundtrip.mncs  executable round-trip laws (u64 verdict codes:
                  0 holds; 1xxx first-parse kind*10+error; 3xxx re-parse;
                  4001/5001 truncation; 1-15 model divergence)
  query.mncs      query-pair lookup + percent-syntax validation
  router.mncs     fixed route table, exact + :param, ANY-method, path_exists
  transport.mncs  memory Pipe with backpressure-as-data
  app.mncs        serve_once/serve_bytes over the default route table
```

Dependency direction is strictly downward: leaves (`error`, `limits`,
`method`, `version`, `status`) ← spans (`uri`, `headers`) ← `message`
← `parser`/`encode` ← `roundtrip`, `router`, `transport`, `query` ←
`app`. No module cycles.

## Parser decomposition (value semantics, no borrows)

MNCS has immutable values and no lifetimes, so the parser splits
responsibilities differently than a borrow-based design:

- The **caller retains bytes** (owns the wire buffer outright).
- The **`Scan` value retains offsets** (phase + token/header/body spans).
- The **`Parser` value retains staged copies** for incremental hosts
  (append by copy; the 1024-byte staging cap bounds the cost).
- **Spans never outlive their buffer** because every function takes the
  buffer alongside the spans it interprets. There is nothing to borrow.

End-of-buffer before a terminal state is `Incomplete`, never a guess;
a positively wrong byte is the only thing that fails. Strict CRLF
framing throughout (bare CR/LF are errors): at a security boundary,
leniency is a smuggling vector.

## Boundaries

- **Corpus/host ABI is flat**: scalars + byte views in, records out.
  In-language code uses rich records freely; corpus-facing functions
  take scalars and views only (record-typed *arguments* need fragile
  identity JSON, so tests synthesize them from a harvested identity
  cache — see `tests/web_exec.py` `ensure_identities`).
- **Errors are data**: hostile bytes produce `Error` codes, never traps.
  `fail` is reserved for internal defects (none reachable in v1).
- **Overflow saturates and reports**: the encoder reports `truncated`
  instead of trapping; pipes report `blocked` instead of waiting;
  reads report emptiness as `kind`.
- **Uniform-1024 convention**: every byte helper takes
  `[byte; up_to 1024]` plus explicit spans, because views cannot narrow
  (WEB-P-006). Lengths are re-validated per helper.

## Decisions

1. **Extension methods preserved** (`Method.EXT` + span): unknown but
   well-formed tokens route and re-encode; only malformed tokens fail.
2. **Transfer-Encoding refused** (501): v1 implements no transfer
   codings, so any non-empty TE is rejected rather than processed as
   identity framing.
3. **Conflicting Content-Lengths rejected**; duplicates that agree are
   accepted (RFC 9110 §8.6).
4. **405 needs `path_exists`**: the router reports path match
   independently of method match, so wrong-method requests get 405.
5. **Reason phrases are advisory**: the encoder emits standard reasons;
   the parser records the peer's reason span without validating it.
6. **No compaction, no pipelining, no HEAD/1xx/chunked/trailer logic**
   in v1 — each refused or ignored explicitly, never silently.
7. **Handler bodies capped at 256 bytes** (`:id` params at 216):
   oversize inputs get exact statuses (414), not truncation.

## Capacities (structural, see `mncs-web.toml`)

wire 1024 · headers 32 · feed chunk 256 · encoder output 1024 ·
reason slot 32 · method slot 8 · handler body 256 · routes 16 ·
route pattern 32 · param splice 216.

Derived ceiling: the 1024-byte encoder output caps response bodies at
roughly 960 bytes (headers take the rest); saturation reports
`truncated` honestly rather than trapping. Handler bodies are capped
far lower (256) so application traffic never approaches the ceiling.

## What is explicitly not built yet

Real sockets (WEB-P-001), middleware/chains (WEB-P-007), transport
interfaces (WEB-P-008), growable/streaming bodies (WEB-P-010), TLS,
cookies/sessions/auth, JSON value support (use `mncs.std.json` cursor
modules), query percent-decoding into buffers, and benchmarks (the code
is structured for future allocation/copy counting).
