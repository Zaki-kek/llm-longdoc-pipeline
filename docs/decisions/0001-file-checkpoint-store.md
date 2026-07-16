# ADR-0001: File-based checkpoint store over a database

**Status:** accepted

## Context
Each generation job needs durable, crash-safe per-job state (which sections are
done, last completed step). Options: a relational DB row per job, an embedded
KV store, or plain files in the job directory.

## Decision
Store job state as `state.json` in the job directory, written atomically via
`temp+rename` on the same filesystem, guarded by an `fcntl` lock, with rotating
backups and auto-repair from the last valid backup on JSON corruption.

## Consequences
- Crash-safety and concurrent-writer safety with zero external infrastructure.
- Trivially inspectable and portable; a job is a directory.
- Trade-off: single-host. A distributed multi-worker deployment would need a
  shared store (S3/Redis/DB). For per-job state on one host this is simpler and
  strictly more debuggable than a DB.
