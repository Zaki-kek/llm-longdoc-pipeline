# ADR-0004: Provider-agnostic LLM layer with fallback

**Status:** accepted

## Context
The pipeline must not be coupled to one vendor SDK, must keep no secrets in
code, and must run offline in tests.

## Decision
Depend only on a small `LLMClient` protocol (`complete(messages) -> str`).
`HTTPChatClient` serves any OpenAI-compatible endpoint from env vars;
`FallbackClient` tries clients in order; `MockLLM` satisfies the same protocol
for offline runs.

## Consequences
- New backend = new class, no pipeline change. Keys live in the environment.
- One provider outage degrades to the next instead of failing the run.
- Trade-off: the lowest-common-denominator chat contract; provider-specific
  features (tools, structured output) would need capability negotiation.
