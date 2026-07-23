"""Main generation loop: brief -> sections -> quality-gated document -> docx.

Three properties make this more than a for-loop over an LLM:

1. Idempotent auto-resume. Every accepted section is checkpointed atomically.
   A crash (or a killed process) is recovered by re-running: sections already
   in the state are skipped, so non-idempotent LLM calls never repeat.

2. Per-section quality gate. Each draft is judged (LLM-as-judge) and revised
   up to a bound before being accepted, so a weak section is caught in place
   instead of surfacing only in the final document.

3. Consistency carry-over. A running summary of prior sections is fed into the
   next section's prompt, keeping a long document coherent end to end.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from pipeline import checkpoints
from pipeline._logging import get_pipeline_logger, new_run_id
from pipeline.chunking import pack_context
from pipeline.context_tracker import ContextTracker
from pipeline.llm_client import LLMClient, client_from_env
from pipeline.metrics import Metrics
from pipeline.prompt_assembler import Brief, section_messages
from pipeline.quality_gate import QualityGate
from pipeline.readability_editor import polish


@dataclass
class Result:
    markdown_path: Path
    docx_path: Path | None
    sections: int
    resumed: int
    metrics: dict | None = None


def generate(
    brief_dict: dict,
    job_dir: Path,
    llm: LLMClient | None = None,
    make_docx: bool = True,
    run_id: str | None = None,
    metrics: Metrics | None = None,
    context_budget: int | None = None,
) -> Result:
    """Generate a document from a brief into ``job_dir``, resumable on crash."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    llm = llm or client_from_env()
    brief = Brief.from_dict(brief_dict)
    run_id = run_id or new_run_id()
    metrics = metrics if metrics is not None else Metrics()
    log = get_pipeline_logger(run_id=run_id, stage="generate")
    provider = getattr(llm, "name", "?")
    gate = QualityGate(llm, metrics=metrics)

    state = checkpoints.read_state(job_dir)
    done: list[dict] = list(state.get("sections", []))
    done_names = {s["section"] for s in done}
    resumed = len(done)

    tracker = ContextTracker()
    tracker.restore(done)

    log.info(
        f"generate.start topic={brief.topic!r} sections={len(brief.sections)} "
        f"provider={provider} resumed={resumed}"
    )

    for section in brief.sections:
        if section in done_names:  # (1) idempotent resume
            continue

        t0 = perf_counter()
        prior = tracker.prior_context()
        if context_budget is not None:
            prior = pack_context(prior.split("\n"), context_budget)
        draft = llm.complete(section_messages(brief, section, prior))

        def revise(feedback: str, _section=section, _prior=prior) -> str:
            msgs = section_messages(brief, _section, _prior + f"\nEditor feedback: {feedback}")
            return llm.complete(msgs)

        accepted = gate.ensure(section, draft, brief.topic, revise)  # (2) judge loop
        finished = polish(accepted, llm)

        tracker.add(section, finished)  # (3) consistency carry-over
        done.append({"section": section, "text": finished})
        checkpoints.write_state_patch(
            job_dir, {"sections": done, "last_step": len(done)}
        )  # atomic checkpoint after each section
        dt = perf_counter() - t0
        metrics.observe("section.duration_seconds", dt)
        log.info(
            f"section.done section={section!r} provider={provider} seconds={dt:.4f}"
        )

    markdown = f"# {brief.topic}\n\n" + "\n\n".join(
        f"## {s['section']}\n\n{s['text']}" for s in done
    )
    md_path = job_dir / "output.md"
    checkpoints.atomic_write_text(md_path, markdown)

    docx_path: Path | None = None
    if make_docx:
        try:
            from pipeline.docx_builder import build_docx

            docx_path = build_docx(
                markdown, job_dir / "output.docx", brief.document_type, brief.topic
            )
        except ImportError:
            docx_path = None  # python-docx not installed; markdown is still produced

    log.info(f"generate.done sections={len(done)} resumed={resumed} provider={provider}")

    return Result(
        markdown_path=md_path,
        docx_path=docx_path,
        sections=len(done),
        resumed=resumed,
        metrics=metrics.snapshot(),
    )
