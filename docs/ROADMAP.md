# Roadmap

Phases after the foundation slice (this run). Ordered by dependency;
each phase is sized for one application-side run after the relevant
language remediation.

## Next: transport reality (needs WEB-P-001)

- Capability-gated socket host behind the `web.transport` verdict
  shapes (`RFC 0002` already maps the calls).
- `Listener` accept loop as a host-driven pump; connection tasks through
  `mncs.std.task.v1` lifecycle.
- Real client → TCP → mncs-web server integration test.
- Without sockets this phase cannot start; do not simulate it with
  more pipes.

## Then: framing completeness

- Chunked transfer coding (negated by the current 501) once streaming
  bodies exist.
- Trailing headers, 1xx interim responses, HEAD-specific body rules,
  `Connection` semantics beyond `close`, keep-alive + pipelining
  (`consumed` already reports the prefix boundary).
- Query percent-decoding into caller buffers; form codec; cookie
  header codec.

## Then: application model

- Handler interfaces the moment callable values land (WEB-P-007):
  replace numeric dispatch, add middleware chains.
- Typed request context, structured errors with problem+json bodies,
  JSON body codec over `mncs.std.json` cursor modules.
- Sessions/auth hooks, static-file boundaries, logging/observability
  hooks with effect declarations.

## Then: machine-native surface

- Self-describing route metadata (method/path/schema registry readable
  by agents at runtime, not generated docs).
- Proof-carrying endpoint contracts where the proof system allows
  (start with resource-limit certificates per route).
- Deterministic replay corpus per service (the test harness already
  records bytes in, bytes out).
- Client-binding generation from the route table.

## Explicitly deferred (non-goals until requested)

Templates/components, CSS tooling, frontend framework, browser engine,
TLS implementation, WebSocket framing (needs socket + framing work
first), HTTP/2-3.
