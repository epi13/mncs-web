# Benchmarks

No micro-benchmark harness exists yet (deliberately: correctness first).
This file records the step-budget baselines measured during foundation
testing so future optimization has something to beat. All figures are
`experiment run` per-case `step_budget` values on
`mncs-research-bytecode` that returned (not exhausted).

## Current budgets (sufficient, not minimal)

| Entry point | Budget | Notes |
|---|---|---|
| leaf scanners (`method.parse`, `status.reason`, …) | 50k | generous; most use < 5k |
| `parse_request` / `parse_response` (≤ 120 B) | 200k | |
| `encode.respond` / `encode_response_view` | 500k | replace-per-byte emission |
| `request_roundtrip` | 1M | parse + encode + re-parse + compare |
| `response_roundtrip` | 500k | encode + parse + compare |
| `feed_pattern`, chunks, ≤ 64 B message | 1M (size 1) / 500k | +1M over 64 B |
| `feed_pattern`, chunks, 96 B message | 2M (size 1) / 1M | fixed ~400k dead-iteration floor |
| `feed_flat` (any split) | 500k | stage_append + full re-parse |
| `serve_once` / `serve_bytes` | 200k | parse + route + encode |
| pipe `write` / `read` | 50–100k | |

## Known cost centers (see WEB-P-003, WEB-P-004)

1. Every emitted/staged byte costs one `replace` over a 1024-byte
   value (no bulk copy primitive).
2. Every `iterate` pays its static capacity (1024/256/32), not the live
   window; dead iterations still evaluate strict-`select` candidates.
3. Re-scanning from the staging start on every feed is O(n²) in feed
   count (accepted for v1; a cursor-retaining scan needs borrow
   support the language does not have).

## Future harness

When `mncs-language` exposes instruction/step accounting per backend
(exact-cost obligations are currently UNKNOWN by design), add:
allocation counts, copies per request, parser passes, header-lookup
comparisons, and dispatch comparisons — all derivable from the corpus
cases already in `tests/`.
