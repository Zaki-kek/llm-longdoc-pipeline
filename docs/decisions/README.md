# Architecture Decision Records

Short, dated records of the load-bearing decisions in this engine: context ->
decision -> consequences. They exist because the *why* behind a design is worth
more than the code that implements it.

- [ADR-0001](0001-file-checkpoint-store.md) - file-based checkpoint store over a database
- [ADR-0002](0002-atomic-substep-and-laststep.md) - one atomic write for substep + last_step
- [ADR-0003](0003-llm-as-judge.md) - LLM-as-judge quality gate that fails open
- [ADR-0004](0004-provider-agnostic-llm.md) - provider-agnostic LLM layer with fallback
- [ADR-0005](0005-mock-llm-in-ci.md) - deterministic mock LLM as a first-class backend
- [ADR-0006](0006-composable-prompts.md) - composable prompts over per-type mega-prompts
