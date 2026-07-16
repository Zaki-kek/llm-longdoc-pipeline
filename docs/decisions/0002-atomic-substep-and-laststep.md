# ADR-0002: One atomic write for substep status + last_step

**Status:** accepted

## Context
Auto-resume decides what to re-run from `last_step`. Marking a substep `done`
and advancing `last_step` used to be two separate locked writes. A crash
between them left `substeps[x]=done` while `last_step` still pointed at the
previous step - resume then re-ran an already-completed step and repeated its
non-idempotent side effects (paid LLM calls, external writes).

## Decision
`mark_substep_done` updates substep status, optional metadata and `last_step`
inside a single `fcntl`-locked atomic write. No window between the two.

## Consequences
- Resume is correct by construction: a step is either fully recorded or not.
- The most expensive failure in a long, paid, multi-call run is eliminated.
