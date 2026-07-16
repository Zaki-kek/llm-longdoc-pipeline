# ADR-0006: Composable prompts over per-type mega-prompts

**Status:** accepted

## Context
Different document types need different instructions. One giant prompt per type
duplicates shared rules and drifts as they are edited independently.

## Decision
Build the system prompt by composing small fragments along independent axes:
`document_type x tone x source`. Adding a type or tone is a data row.

## Consequences
- Prompts are diff-able, testable and free of copy-paste drift.
- Trade-off: very type-specific phrasing is harder to express than in a bespoke
  prompt; acceptable for a structured-document generator.
