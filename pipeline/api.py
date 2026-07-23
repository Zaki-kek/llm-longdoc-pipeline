"""Thin typed in-process facade over the generation engine.

This is the library integration surface: a single ``run(brief, out_dir, ...)``
call plus a frozen, validated ``RunConfig`` of the public knobs. It is a
deliberately small adapter over ``orchestrator.generate`` - no web framework,
no server, no behavior of its own beyond mapping config fields to kwargs and
(optionally) wrapping the client in a persistent cache.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.cache import CachingClient, FileCache
from pipeline.llm_client import LLMClient, client_from_env
from pipeline.orchestrator import Result, generate


@dataclass(frozen=True)
class RunConfig:
    """Immutable set of public run knobs, validated on construction."""

    make_docx: bool = True
    context_budget: int | None = None
    use_cache: bool = False
    run_id: str | None = None

    def __post_init__(self) -> None:
        if not (self.context_budget is None or self.context_budget > 0):
            raise ValueError("context_budget must be None or a positive int")


def run(
    brief: dict,
    out_dir: str | Path,
    llm: LLMClient | None = None,
    config: RunConfig | None = None,
) -> Result:
    """Run the generation engine over ``brief`` into ``out_dir``.

    A thin typed wrapper around ``orchestrator.generate``: it maps the frozen
    ``RunConfig`` onto ``generate``'s kwargs and, when ``config.use_cache`` is
    set, wraps the client in a persistent content-hash cache under
    ``out_dir/llm_cache.json``. It does not change generation behavior.
    """
    cfg = config if config is not None else RunConfig()
    out_dir = Path(out_dir)
    client = llm if llm is not None else client_from_env()
    if cfg.use_cache:
        client = CachingClient(client, store=FileCache(out_dir / "llm_cache.json"))
    return generate(
        brief,
        out_dir,
        llm=client,
        make_docx=cfg.make_docx,
        run_id=cfg.run_id,
        context_budget=cfg.context_budget,
    )
