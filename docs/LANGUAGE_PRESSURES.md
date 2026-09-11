# MNCS language pressure ledger

This file records genuine `mncs-language` pressures discovered while
implementing `mncs-web`. Each entry follows the mission format (ID,
severity, category, workload, reproducer, expected/actual, workaround
and its cost, desired capability, affected projects, evidence).

Conventions:

- Severity: `blocker` (cannot build the component), `major` (forces
  architecture-wide workaround), `minor` (local workaround, papercut).
- Status: `open` (confirmed this run), `known` (already tracked
  upstream; this entry adds mncs-web evidence), `rejected` (investigated,
  not a language issue).
- `mncs-language` here means the language/compiler/runtime/stdlib as a
  whole; each entry names the likeliest owner.
- Nothing here was worked around by modifying the language. All
  workarounds live in `mncs-web` source, are isolated, and cite the
  pressure ID at the workaround site.

## WEB-P-001 — No socket/network capability in the language

- Status: open
- Severity: blocker (for real networking; the rest of the stack proceeds
  without it)
- Category: OS/runtime

What mncs-web was trying to implement: a TCP listener/connection backing
for `web.transport` (`Listener`, `Connection`), and the
client -> TCP -> mncs-web server integration milestone from the mission.

Expected behavior: an explicit capability-gated socket interface
(connect/listen/accept/read/write with HIPAA-style effect declarations),
or at minimum a documented refusal roadmap.

Actual behavior: no socket, TCP, UDP, DNS, or generic network handle
exists in any profile (0.1-0.13), the standard library, or the effects
spec beyond a SHOULD-level statement that network authority must be
explicit (`spec/effects-and-capabilities.md`). Searched
`library/`, `spec/`, and all source profiles for
socket/tcp/network/http: no hits in the language surface.

Why this is a language/runtime issue: networking is a runtime/host
capability, not something an application repo can soundly invent (effect
model, authority, backend portability all belong to the language).

Current workaround: `web.transport.v1` is a memory-backed `Pipe` with
backpressure-as-data; all integration tests run through pipes and the
`serve_bytes` boundary. Transport dependencies are isolated behind the
Pipe shape so a future socket host can slot in.

Cost of the workaround: no real network I/O is possible; the
client/server milestone stops at the process boundary; every framing
decision must be re-validated once a real transport exists.

Desired capability: capability-gated byte-stream connect/listen/accept
with explicit effects, or a tracked RFC with milestones.

Other projects likely affected: mncs-service, mncs-fabric, mncs-engine,
any distributed MNCS system.

Evidence/tests: `src/web/transport.mncs`, `tests/test_transport.py`
(pipe loopback stands in for the socket test).

## WEB-P-002 — Exact-array record fields cannot borrow as bounded views

- Status: open (likely new; the Profile 0.7 borrow rule lists value
  positions but not field projections)
- Severity: major
- Category: type system / ownership-lifetime-adjacent (borrow rules)

What mncs-web was trying to implement: passing `parser.staged`
(`[byte; 1024]` field of the `Parser`/`StageAcc` record) directly to
`run_parse(buf: [byte; up_to 1024], ...)`.

Minimal reproducer: `repro/borrow-field-view.mncs` (`via_field` fails;
`via_direct` with the identical type elaborates).

Expected behavior: the exact-to-view borrow (`N <= M`, no copy, alias
semantics per Profile 0.7) fires for a field projection exactly as it
does for a named value, call result, or argument.

Actual behavior: `MNE163` (projected field does not have the required
expression type) on the field-to-view coercion in argument, annotated
`let`, and return positions (all three probed).

Why this appears to be a language/compiler issue: the borrow is
semantically identical (immutable alias, bound preserved); only the
projection path refuses it. The 0.7 rule enumerates positions but never
excludes projections, so this reads as an implementation gap, not a
designed restriction.

Current workaround: rebind through a same-type local first
(`let staged_view: [byte; 1024] = grown.staged;`), then borrow from the
local. Three sites in `src/web/parser.mncs` (`parser_feed`,
`feed_flat`, `feed_pattern`), each citing WEB-P-002.

Cost of the workaround: one nominal 1024-byte copy per incremental feed
(semantically; backends may alias immutables), plus a non-obvious rule
every contributor must learn. The workaround is small and grep-able.

Desired capability: extend the exact-to-view borrow to field (and
ideally chained) projections, or document the exclusion with a dedicated
diagnostic suggesting the rebind.

Other projects likely affected: mncs-store (chunk framing over record
fields), mncs-crypto (state records), any parser holding buffers in
records — i.e. all three confirmed parser-like workloads.

Evidence/tests: `repro/borrow-field-view.mncs` (1 error, MNE163);
workaround sites pass the full suite (`tests/test_fragmentation.py`).

## WEB-P-003 — No bulk span-copy primitive (replace-per-byte emission)

- Status: open
- Severity: minor (correctness unaffected; performance and step budgets)
- Category: stdlib / optimizer / memory (buffers/slices)

What mncs-web was trying to implement: `emit_span` (copy a parsed span
into the encoder output) and `stage_append` (stage a feed chunk) as
single bounded operations.

Expected behavior: a total `copy_span(dst, dst_at, src, src_at, len)`
with explicit bounds failure, compiling to a memmove-like backend op.

Actual behavior: no such primitive exists in `mncs.core`/`mncs.std`;
every byte is placed with one `replace` (each `replace` rebuilds the
1024-byte value semantically). `feed_pattern` with 1-byte chunks over a
37-byte message needs a ~1M step budget; the same logic with bulk copies
would be ~2 orders of magnitude cheaper in steps.

Why this is a language/stdlib issue: only the compiler can provide a
bounds-checked bulk op that lowers efficiently on all five backends;
user code cannot beat per-element `replace` in step cost.

Current workaround: per-byte `replace` loops with strict-`select`
gating (total, no traps). Budgets sized accordingly
(`feed_pattern` cases run at 1M steps).

Cost of the workaround: step-budget inflation for all chunked paths;
host-side O(n*m) byte movement in tests; future throughput work will
hit this wall first.

Desired capability: `mncs.core`/`mncs.std` bounded `copy_span` (or
`blit`) with identical semantics on all backends.

Other projects likely affected: mncs-store (frame building),
mncs-media, mncs-crypto (block ops).

Evidence/tests: `src/web/encode.mncs` (`emit_span`), step-budget data
in `tests/test_fragmentation.py` (1M budget for 1-byte feeds).

## WEB-P-004 — Bounded iteration always pays the static capacity

- Status: open
- Severity: minor (budget pressure, not correctness)
- Category: semantics / optimizer (bounded iteration)

What mncs-web was trying to implement: `stage_append` over a runtime
`take <= 256` and `feed_pattern` over short messages without paying for
the full 1024-slot staging capacity on every feed.

Expected behavior: iteration cost proportional to the live window
(`take`, `hlen`), with dead iterations either skipped or provably free.

Actual behavior: `iterate` traverses the static bound (1024 for the
staging buffer, 256 for chunks) and every dead iteration still
evaluates both `select` candidates (strictness), including a full
`replace`. The first `stage_append` shape (iterate the 1024 staging
buffer) blew the 200k budget on a 37-byte message; restructuring to
iterate the 256 chunk fixed it, but short takes still pay 256.

Why this is a language issue: bounds must be static for verification,
but the compiler could specialize on the (already computed) runtime
length, or offer an explicit bounded-prefix traversal form. Application
code cannot express "exactly the first `take` slots" as a traversal
domain today.

Current workaround: iterate the smallest statically-sized value
available (chunk, not staging buffer); size budgets generously.

Cost of the workaround: 4-8x step overpayment on small feeds; budget
planning per entry point; throughput ceiling for chunked protocols.

Desired capability: runtime-length-bounded traversal (or optimizer
specialization) with the same static guarantees.

Other projects likely affected: every bounded-buffer protocol workload.

Evidence/tests: `feed_pattern` 1M-budget cases; the stage_append
restructure (commit history) shows the before/after shape.

## WEB-P-005 — Integer literals coerce only on the right of binary ops

- Status: open (likely new; small, high-confidence)
- Severity: minor
- Category: compiler diagnostics / ergonomics (type system)

What mncs-web was trying to implement: `1000 +% (kind *% 10) +% err`
(u64 arithmetic with literal magnitudes).

Minimal reproducer: `repro/literal-left-coercion.mncs` (`right_*`
elaborate; `left_*` fail).

Expected behavior: symmetric literal adaptation (or a refusal in both
positions with the same message).

Actual behavior: `MNE119` fires only when the literal is on the left;
the identical literal on the right coerces silently. The asymmetry is
undocumented in the profile material and surprising: commutativity of
`+%`/`*%` does not extend to elaboration.

Why this appears to be a compiler issue: the coercion rule is
positional rather than type-directed; nothing in the spec justifies the
left/right difference.

Current workaround: keep every literal on the right
(`(kind *% 10) +% err +% 1000`). Three sites in
`src/web/roundtrip.mncs`; one named binding (`let cap: u64 = 1024;`)
in `src/web/transport.mncs`.

Cost of the workaround: trivial once known; a papercut for every new
contributor (the error message does not suggest commuting operands).

Desired capability: symmetric literal coercion, or an MNE119 message
that suggests moving the literal to the right operand.

Other projects likely affected: all MNCS application code doing
mixed literal/variable arithmetic.

Evidence/tests: `repro/literal-left-coercion.mncs` (MNE119 x2).

## WEB-P-006 — Bounded views cannot be narrowed (known; new cost evidence)

- Status: known (Profile 0.7 documents view-to-view relaxation as future
  work) — this entry adds mncs-web cost evidence, not a new claim.
- Severity: minor (architecture-wide convention, locally cheap)
- Category: type system (buffers/slices)

What mncs-web was trying to implement: narrow helpers, e.g. a header
name matcher taking `[byte; up_to 64]` over the shared wire buffer, or
slicing a query window out of the request buffer at a smaller bound.

Minimal reproducer: `repro/view-narrow.mncs` (MNE188/MNE133); the
positive control (same-capacity slice) elaborates.

Expected behavior (long term): a total narrowing borrow with an
explicit runtime range check, per the 0.7 future-work note.

Actual behavior: any capacity change on slicing/borrowing is refused;
all 15 mncs-web modules take the single widest capacity
(`[byte; up_to 1024]`) plus explicit spans, and every length is
re-validated per helper instead of once at the narrowing point.

Current workaround: uniform-1024 convention (documented in
ARCHITECTURE.md). No per-site hacks; the cost is convention overhead
and repeated window checks.

Cost of the workaround: helper signatures are wider than their true
domains; each helper re-derives `hlen`; a future narrowing primitive
will simplify ~40 signatures at once (mechanical migration).

Desired capability: whatever the 0.7 future-work item tracks; mncs-web
is a ready-made migration corpus and conformance suite for it.

Other projects likely affected: mncs-store, mncs-doc, any multi-layer
byte pipeline.

Evidence/tests: `repro/view-narrow.mncs`; the uniform-1024 convention
across `src/web/*.mncs`.

## WEB-P-007 — No first-class handlers/closures (numeric dispatch)

- Status: open (expected; structural language scope, not a regression)
- Severity: major (shapes the application layer)
- Category: type system / semantics (higher-order functions)

What mncs-web was trying to implement: a `Router` mapping paths to
handler functions/closures, and middleware as composable function
values (`Handler`, `Middleware` in RFC 0001 terms).

Expected behavior: first-class (possibly bounded/linear) function
values so routes and middleware compose as values.

Actual behavior: Profile 0.13 explicitly leaves "unrestricted callable
values" out of scope; routes map to `u64` handler ids and
`web.app.dispatch` is an integer `match` over them.

Why this is a language issue: dynamic handler registration and
middleware composition cannot be expressed without callable values;
the numeric-dispatch table is the only total encoding available.

Current workaround: `Route.handler: u64` + exhaustive integer match in
`dispatch` (unknown ids fall through to 404). Middleware does not exist
in v1.

Cost of the workaround: adding a route means touching the table, the
id registry, and the dispatch match (three sites, no static link
between them); middleware/chains are unrepresentable; handler
unit-testing goes through `serve_once` rather than direct calls.

Desired capability: bounded callable values (or a vetted handler-registry
pattern in stdlib) with exhaustiveness checking preserved.

Other projects likely affected: mncs-service, mncs-ui (callbacks),
mncs-cli (subcommands).

Evidence/tests: `src/web/router.mncs` (`handler: u64`),
`src/web/app.mncs` (`dispatch`), `tests/test_app.py`.

## WEB-P-008 — No traits/interfaces for transport abstraction

- Status: open (expected; structural language scope)
- Severity: major (shapes the io layer)
- Category: type system (traits/interfaces)

What mncs-web was trying to implement: `Reader`/`Writer`/`Stream`/
`Connection`/`Listener` as interfaces with memory, socket, file, and
test implementations behind them (mission: "alternate backends").

Expected behavior: interface/trait abstraction with static dispatch
(or bounded dynamic dispatch) so transports are substitutable.

Actual behavior: Profile 0.13 leaves traits out of scope; generic
functions exist but generic *nominal* declarations do not, and there is
no interface mechanism. `web.transport.Pipe` is a concrete record with
free functions; socket/file transports cannot implement a shared
interface and must instead duplicate the function vocabulary by
convention.

Current workaround: concrete `Pipe` + documented function-shape
contract (`pipe_write`/`pipe_read` backpressure-as-data verdicts) that
future transports must mirror. No machinery pretends otherwise.

Cost of the workaround: substitutability is conventional, not checked;
generic server code over transports cannot be written once.

Desired capability: traits/interfaces (or a recorded decision for an
alternative abstraction story) sufficient for Reader/Writer/Stream.

Other projects likely affected: mncs-service, mncs-store (backends),
mncs-engine (device streams).

Evidence/tests: `src/web/transport.mncs`, ARCHITECTURE.md transport
section.

## WEB-P-009 — Bounds obligations stay UNKNOWN (proof/contracts ceiling)

- Status: open
- Severity: minor (honesty preserved; automation missing)
- Category: proofs/contracts

What mncs-web was trying to implement: discharging "cursor never
exceeds input bounds" statically for the guarded-projection discipline
(`slot` clamped to a valid index before every dynamic projection), so
the parser's hot loop carries no residual runtime checks.

Expected behavior: the obligation system discharges checks the
programmer has made statically redundant (clamped index, capacity
proof), or names the exact missing lemma.

Actual behavior: every dynamic projection retains a RuntimeChecked
obligation in UNKNOWN state (visible as CMP301 notes); the code is
correct by construction plus runtime checks, but the proof system
contributes no discharge and no check can be removed. The
clamp-then-project pattern (borrowed from `mncs.std.text_scan.v1`) is
provably safe by inspection yet indistinguishable from unguarded
indexing in the obligation ledger.

Current workaround: none needed for soundness (runtime checks hold);
the pressure is the absence of proof leverage, not a workaround.

Cost: defense-in-depth checks that a stronger system could erase;
no machine-checked connection between the clamp and the projection.

Desired capability: bound-clamp discharge rules (or an explicit
"checked-index" form whose obligation the kernel closes by
construction).

Other projects likely affected: every bounds-sensitive MNCS program.

Evidence/tests: CMP301 notes on every `source-study` run; the guarded
projection discipline documented in `src/web/method.mncs`
(`token_valid`) and ARCHITECTURE.md.

## WEB-P-010 — No growable buffers (fixed capacities are structural)

- Status: open (expected; memory-model scope)
- Severity: major (caps the protocol surface)
- Category: memory

What mncs-web was trying to implement: request/response bodies beyond
1024 bytes, header blocks beyond 32 entries, routes beyond 16, reason
tables without padded slots.

Expected behavior: growable (still bounded, still explicit) buffers, or
a streaming body API that does not require staging the whole body.

Actual behavior: no heap allocation exists in any profile; every
capacity is a structural constant (`[byte; 1024]`, `[Header; 32]`,
`[Route; 16]`, `[byte; 256]` bodies). Bodies larger than the wire
buffer cannot be represented; `BodyTooLarge`/`HeadTooLarge` are load-
bearing API, not just hardening.

Current workaround: v1 caps (documented in `mncs-web.toml`
`[capacities]`), span-based zero-copy bodies within the buffer,
explicit errors past the caps. No fake streaming.

Cost of the workaround: the stack tops out at small-message workloads
(health checks, small JSON APIs); file upload, SSE/EventStreams scale,
and large-header workloads are out of scope until the memory story
lands.

Desired capability: bounded growable buffers (or first-class streaming
body/structure support) with explicit limits preserved.

Other projects likely affected: mncs-store (multi-chunk objects),
mncs-media, mncs-doc.

Evidence/tests: `[capacities]` in `mncs-web.toml`;
`BodyTooLarge`/`HeadTooLarge` cases in `tests/test_parser.py`.

## WEB-P-011 — Record corpus field order: bytecode accepts declaration order, compiled backends demand canonical order

- Status: open
- Severity: major (silent cross-backend divergence; every synthesized
  record argument was rejected on wasm)
- Category: compiler/backends (value-contract validation)

What mncs-web was trying to implement: corpus arguments carrying
synthesized records (`HeaderBlock` for header lookup, `RouteTable` for
custom-table routing, `Parser` for record-threading paths).

Expected behavior: record fields match by name (MNCS records are
nominal, name-matched values), so field order in a corpus argument
should not matter — or the corpus schema should state a canonical
order.

Actual behavior: the bytecode interpreter accepts record fields in
source declaration order, but `mncs-portable-wasm-mvp` rejects the
same argument with `invalid_request: backend request violates the
language-owned value contract`. Reordering fields alphabetically —
the order used in the `type_identity` spelling — is accepted on wasm
AND on bytecode with identical results. The compiled-backend check
(`backend_input_matches` in `mncs-codegen/src/lib.rs`) zips contract
fields with value fields positionally (`name == field_name` per
position), so any order other than the contract's canonical order
fails. The contract order is alphabetical for every record observed
(`Route`, `RouteTable`, `Header`, `HeaderBlock`, `Parser`,
`ParseOut`, `GetOut`).

Why this is a language/runtime issue: two conforming backends
disagree on whether a valid value is valid. Either the corpus schema
should mandate canonical field order (and the bytecode backend should
enforce it, so producers learn the rule), or the compiled-backend
check should match fields by name. Today the lenient backend teaches
producers an order the strict backends reject, and the rejection
carries no hint (no expected-vs-actual field listing).

Worse, the strictness is only skin-deep: top-level record fields are
validated positionally (wrong order rejected), but NESTED records
inside sequences pass validation unchecked (`scalar_field_matches`
returns true for any sequence) and are then bound positionally —
declaration-order nested records are silently misread instead of
rejected. Demonstrated in the reproducer: canonical top-level order
with declaration-order nested `Header` values returns
`found: false` for a present header (the spans bind to the wrong
fields); fully canonical order returns the correct span. A rejection
would be a papercut; a silent wrong read is a soundness hole in
cross-backend corpus validity.

Current workaround: `REC` in `tests/web_exec.py` sorts fields into
canonical (alphabetical) order at every nesting level; nested RECs
are sorted recursively by construction. Guarded by
`tests/test_harness.py`.

Cost of the workaround: trivial in code, but every downstream corpus
producer must independently discover the canonical-order rule; the
divergence stays a trap for other projects until the backends agree.

Desired capability: backends agree — either all enforce canonical
order with a diagnostic that names the expected order, or all match
by name.

Other projects likely affected: any project synthesizing record
corpus arguments (mncs-store, conformance suites).

Evidence/tests: `repro/record-field-order.py` (same call, both
orders, prints both verdicts); `tests/test_harness.py`;
wasm `invalid_request` failures in the pre-fix full-matrix log
(`test_header_block_ops`, `test_custom_table_priority_and_wildcard`,
`test_parser_record_paths`).

## WEB-P-012 — Native backends trap past small feed-staging counts

- Status: open
- Severity: major (the full chunk-convergence battery can only run on
  the interpreter; every native backend needs a reduced matrix)
- Category: compiler/backends (codegen resource scaling)

What mncs-web was trying to implement: chunk-size convergence —
`feed_pattern` staging the same message in 1, 5, and 64-byte pieces
must converge with the one-shot parse, on every backend.

Expected behavior: staging N chunks costs steps, not soundness. Past
any resource limit the backend should report budget exhaustion (or a
named resource error), identically to the interpreter.

Actual behavior: past a small, backend-specific live-chunk count, the
same corpus that converges on `mncs-research-bytecode` dies on every
native backend, each in its own way:
- `mncs-portable-wasm-mvp`: `runtime_failure: backend trap:
  out-of-bounds memory store` at 13+ live chunks (12 verified good).
- `mncs-cranelift`: `cranelift JIT cell access exceeded the arena
  image; failing closed` (same 13-chunk trigger).
- `mncs-c11` / `mncs-llvm-ir`: bare `runtime_failure` with null
  reason at 1 step — no diagnostic at all (10 live chunks fails; 1-2
  verified good).
Verified brackets (live `fold_feed` chunks, 37 B message unless
noted): wasm 12 pass / 13 trap; c11 1 pass / 10 fail; llvm and
cranelift 2 pass (upper range unprobed); 5 B message at chunk size 1
(5 live) passes on wasm. The trigger tracks live-chunk count, not
message bytes (23 B in 12 chunks passes; 37 B in 13 chunks traps).

Why this is a language/runtime issue: identical MNCS source
traps/fails-opaquely on native backends while the reference
interpreter converges. Application code cannot distinguish "too many
chunks" from correct code, and two backends give no actionable
diagnostic (null reason; arena internals). Suspected family:
loop-carried large-array temporaries (`build_chunk` 256 B carrier +
1024 B staged copies per live chunk) exhausting per-backend
memory/arena sizing — but that is a guess from symptoms, for the
backend owners to confirm.

Current workaround: per-backend live-chunk ceilings in
`tests/test_fragmentation.py` (`BACKEND_LIVE_CAP`: bytecode full
battery; wasm 12; c11/llvm/cranelift 2), with every excluded
(chunk-size, backend) pair printed and tabulated instead of silently
skipped. Unknown backends fail closed (explicit ceiling required).

Cost of the workaround: convergence is proved in full only on the
interpreter; native-backend portability covers 1-12 chunks depending
on backend. If backend ceilings move, the caps must be re-verified by
execution (the table records exactly what was verified).

Desired capability: native backends stage arbitrary chunk counts
like the interpreter, or refuse with a named, actionable resource
error — never a trap or a null-reason failure.

Other projects likely affected: any project looping over
large-array temporaries on native backends (mncs-store chunking,
mncs-media frames).

Evidence/tests: `repro/feed-chunk-trap.py` (5-live control +
13-live trigger on any backend); `BACKEND_LIVE_CAP` and SKIP lines in
`tests/test_fragmentation.py`; coverage table in `tests/README.md`.

## Investigated but rejected (not language pressures)

- `!=` on integers/bytes: suspected missing, actually present (probed
  `u64 != u64` and `byte != byte`: 0 errors). The codebase uses
  `!(x == y)` in older spots purely from caution; no change needed.
- Same-capacity view slicing (`buf[s..e]` at unchanged capacity):
  works (0 errors). Only *narrowing* is refused (WEB-P-006).
- `select` over sequences/records/bytes: works (probe: sequence, byte,
  and record selections all elaborate and execute). Strictness (both
  sides evaluate) is real but documented and designed, not a defect.
- `iterate` over exact arrays, local arrays, and record-field arrays:
  all elaborate. The cost model (WEB-P-004) is the pressure, not the
  mechanism.
- Async runtime absence: correctly out of language scope for this
  milestone (structured `mncs.std.task.v1` lifecycle + host-driven I/O
  is the honest decomposition, mirroring mncs-store). Not filed.
- `repeat [value; N]` with symbolic N: refused by design (MNP203,
  documented in 0.13). Filed nowhere; the padded-literal and
  fill-loop patterns cover v1 needs.
- `fail`/`next` as identifiers: reserved words, correctly rejected with
  precise diagnostics. Ergonomics note at most; not filed.
- Round-trip TE law code 1036 vs expected 2036: suspected codec
  regression, actually a stale test expectation. The implementation
  follows its own tier scheme (`1000 + kind*10 + error` for first-parse
  failure); kind 2 + error 16 (`UnsupportedTransfer`) yields 1036, and
  no 2xxx tier exists in `request_roundtrip`. Fixed the test, not the
  source (`tests/test_roundtrip.py`).
