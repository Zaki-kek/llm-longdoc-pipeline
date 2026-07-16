# ADR-0005: Deterministic mock LLM as a first-class backend

**Status:** accepted

## Context
CI must be fast, free and deterministic, but the value is in the control flow
(resume, judge loop, checkpointing), not in a specific model's prose.

## Decision
`MockLLM` implements the `LLMClient` protocol and returns fixed,
stage-appropriate text. The full pipeline and all tests run on it with no key
and no network.

## Consequences
- Tests exercise real orchestration, not stubbed-out branches.
- A fresh checkout produces a document out of the box.
- Trade-off: the mock does not test prompt quality; that is validated
  separately against a live provider.
