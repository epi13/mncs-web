# mncs-web

Machine-native web application infrastructure for MNCS.

`mncs-web` is an application-level pressure project for `mncs-language`: it should make ordinary HTTP and web-service development concise without giving up explicit machine semantics, typed effects, deterministic behavior where requested, or inspectable execution.

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

- `docs/ARCHITECTURE.md` — architectural boundaries and staged build plan
- `docs/rfcs/0001-foundation.md` — foundational design RFC
- `docs/LANGUAGE_PRESSURES.md` — language/runtime/compiler pressure ledger
- `AGENTS.md` — contributor and agent operating contract

Implementation should be written in `mncs-language` as the language becomes capable enough. Missing language capabilities are findings to document, not reasons to silently replace core implementation with another language.
