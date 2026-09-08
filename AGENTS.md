# Agent and contributor contract

Work in this repository should advance `mncs-web` while using it as a deliberate `mncs-language` pressure test.

- Prefer `mncs-language` for implementation.
- Keep public APIs small, composable, typed, and machine-inspectable.
- Do not hide missing language/runtime/compiler capabilities behind permanent foreign-language substitutes.
- Record concrete blockers and awkward patterns in `docs/LANGUAGE_PRESSURES.md` with a minimal reproducer or required semantic when possible.
- Separate application-framework requirements from changes that belong in `mncs-language`, the standard library, compiler, runtime, Fabric, or other MNCS repositories.
- Preserve deterministic and testable semantics where they are promised; do not infer correctness from compilation alone.
- Add tests with each implemented behavior and prefer end-to-end examples that exercise realistic web workloads.
