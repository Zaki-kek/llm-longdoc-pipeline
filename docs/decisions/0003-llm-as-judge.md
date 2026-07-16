# ADR-0003: LLM-as-judge quality gate that fails open

**Status:** accepted

## Context
Per-section quality needs to be checked before the section is accepted. A regex
/ rule validator is cheap but blind to meaning; a human is out of the loop.

## Decision
A separate judge call classifies each draft `READY` / `NEEDS_FIXES: <reasons>`
and drives up to N feedback-guided revisions. A malformed judge reply is
treated as `READY` (fail-open).

## Consequences
- Catches weak sections in place instead of at the end.
- Fail-open is deliberate: the judge is an improver, not a gate that can
  deadlock generation on its own bad output. The revision count is bounded so
  the loop always terminates.
- Trade-off: extra LLM calls per section. Worth it for long documents where a
  single bad section is expensive to find later.
