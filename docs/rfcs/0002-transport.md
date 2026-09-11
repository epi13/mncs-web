# RFC 0002: Transport interface (memory pipes now, sockets later)

Status: Accepted (v1 memory scope)

## Purpose

Define the transport boundary so `mncs-web` never hard-codes a socket
API it cannot yet name, while giving a future socket host an exact
contract to implement.

## v1 contract (`web.transport.v1`)

A transport moves opaque bytes between exactly two parties with:

- `write(bytes) -> accepted | blocked` — all-or-nothing staging;
  `blocked` is backpressure as data, never a wait.
- `read(max) -> data | empty` — emptiness as data (`kind`), never a
  block; `length` is always exact.
- `available`, `free` accounting over a fixed 1024-byte staging buffer.
- Single request/response exchange per pipe (no compaction in v1).

The memory `Pipe` implements this contract directly. A test driver (or
host loop) retries or cancels between attempts, exactly like the
`mncs.std.channel.v1` drain discipline this contract mirrors.

## Socket mapping (future, blocked on WEB-P-001)

A socket host implements the same verdicts over real file descriptors:

```text
pipe_write  ->  send(2) with EAGAIN mapped to blocked
pipe_read   ->  recv(2) with EAGAIN mapped to empty
available   ->  ioctl(FIONREAD) or epoll readiness (host detail)
```

Framing, parsing, routing, and encoding stay unchanged: they only ever
see staged bytes. The `serve_bytes` boundary (bytes in, bytes out) is
already socket-shaped; only the pump needs authority the language does
not yet grant.

## Non-goals for v1

No `Listener` (accept loop needs scheduler + socket authority), no TLS
terminology in the interface, no compaction/corking knobs, no
half-close states. Each gets an RFC when its language capability lands.
