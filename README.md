# mncs-web

Machine-native web application infrastructure for MNCS.

`mncs-web` is an application-level pressure project for `mncs-language`: it should make ordinary HTTP and web-service development concise without giving up explicit machine semantics, typed effects, deterministic behavior where requested, or inspectable execution.

> **Status:** foundation vertical slice implemented and validated
> (2026-09-10). Typed HTTP/1.x protocol structures, an incremental byte
> parser as an explicit state machine (requests + responses),
> request/response encoders, in-language round-trip laws, memory-backed
> transport pipes, a deterministic router, and a request → handler →
> response slice, with a pytest suite driving real MNCS executions.
> Full suite green (48 tests) on all five backends
> (`mncs-research-bytecode`, `mncs-portable-wasm-mvp`, `mncs-c11`,
> `mncs-llvm-ir`, `mncs-cranelift`). The chunk-convergence battery
> runs in full on bytecode; native backends run the within-ceiling
> subset (WEB-P-012, ceilings tabulated in `tests/README.md`).
> See `docs/ARCHITECTURE.md` and `docs/LANGUAGE_PRESSURES.md`.

## Initial scope

- HTTP request/response primitives and routing
- middleware and typed request context
- JSON, forms, multipart data, cookies, and sessions
- async I/O, streaming, WebSockets, and backpressure
- authentication/authorization integration points
- server-side rendering/component integration
- observability, configuration, and deployment boundaries

## Machine-native goals

The framework should expose enough structure for MNCS tooling to reason about routes, effects, data flow, permissions, resource use, and failure paths rather than treating the application as opaque callbacks.

## Repository layout

- `src/web/` — MNCS implementation (Profile 0.13, 15 modules)
- `tests/` — pytest suite driving real MNCS executions (`tests/README.md`)
- `repro/` — minimized language reproducers backing pressure entries
- `docs/ARCHITECTURE.md` — architectural boundaries and decisions
- `docs/rfcs/0001-foundation.md` — foundational design RFC
- `docs/rfcs/0002-transport.md` — transport interface RFC
- `docs/LANGUAGE_PRESSURES.md` — language/runtime/compiler pressure ledger
- `mncs-web.toml` — project manifest, backends, structural capacities
- `scripts/run_suite.sh` — full validation (study + tests)
- `AGENTS.md` — contributor and agent operating contract

Implementation is written in `mncs-language`. Missing language capabilities are findings to document, not reasons to silently replace core implementation with another language.

## Quick start

```bash
# validate every module (needs the mncs-language checkout beside this repo)
./scripts/run_suite.sh
# fast iteration on one area
MNCS_BACKENDS=mncs-research-bytecode python3 -m pytest tests/test_parser.py -q
```

`MNCS_BIN` and `MNCS_LANG_LIB` override the compiler binary and library
path; `MNCS_BACKENDS` selects backends (default: research-bytecode and
portable-wasm, which need no external toolchain).
