# RFC 0001: mncs-web foundation

Status: Draft

## Purpose

Define `mncs-web` as the canonical high-level web pressure project for MNCS and establish the contracts that future implementation must preserve.

## Principles

- Ergonomics is a correctness requirement: common web tasks should remain concise and diagnosable.
- Network, filesystem, clock, randomness, process and credential access are explicit effects.
- Async work has structured lifetime, cancellation and backpressure semantics.
- Route and middleware composition remains statically inspectable where practical.
- User-controlled bytes are untrusted until parsed/validated.
- Fast paths must not erase safety or observability contracts.

## Initial interface domains

HTTP messages, router, handler/context, body streams, middleware, errors, serialization, sessions, authentication hooks, WebSockets and server lifecycle.

## Pressure objectives

This project should specifically expose weaknesses in async/await, closures, generics, sum/optional types, strings/Unicode, byte buffers, effect modeling, cancellation, error propagation, reflection/schema support, package ergonomics, diagnostics and FFI/runtime networking.

## Non-goals for the bootstrap phase

No large framework implementation, browser engine, bespoke TLS implementation, or replacement of proven cryptographic/network primitives. The first phase establishes contracts and representative workloads before breadth.
