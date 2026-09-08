# MNCS language pressure ledger

This file records pressure discovered while implementing `mncs-web`.

For each finding record:

- **ID / status**
- **workload** that exposed it
- **current MNCS behavior**
- **required semantic or ergonomic behavior**
- **minimal reproducer** when possible
- **likely owner** (`mncs-language`, stdlib, compiler, runtime, Fabric, or this repo)
- **temporary workaround**, if any
- **verification required** before closing

## Initial pressure targets

- async I/O, structured concurrency, cancellation and deadlines
- borrow/ownership behavior across awaits and streams
- closures and handler composition
- typed heterogeneous request context
- byte buffers and zero-copy slices
- Unicode/string ergonomics
- optional/sum types and error propagation
- schema/serialization support
- effect declarations for network/filesystem/clock/randomness
- diagnostics for common application mistakes

No pressure item should be marked resolved solely because a workaround compiles.
