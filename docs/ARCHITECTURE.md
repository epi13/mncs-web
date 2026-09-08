# Architecture

`mncs-web` is intended to sit above MNCS networking/runtime primitives and below user applications.

## Layers

1. **Protocol primitives** — HTTP messages, headers, bodies, status, parsing/serialization boundaries.
2. **Execution** — server lifecycle, async I/O, cancellation, deadlines, streaming, backpressure.
3. **Application model** — routing, middleware, typed context, errors, configuration, sessions and auth hooks.
4. **Presentation** — structured responses, templates/components, WebSockets and event streams.
5. **Evidence and tooling** — route graph inspection, tracing, resource/effect metadata, test fixtures and benchmarks.

## First milestones

1. Minimal HTTP server and typed router.
2. JSON request/response plus structured errors.
3. Async streaming and cancellation semantics.
4. Middleware/context and observability.
5. Sessions/auth boundaries and WebSockets.
6. Ergonomic examples and benchmark/pressure corpus.

The architecture should remain usable by small applications without forcing the full stack.
