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

from pipeline import checkpoints
from pipeline.context_tracker import ContextTracker
from pipeline.llm_client import LLMClient, client_from_env
from pipeline.prompt_assembler import Brief, section_messages
from pipeline.quality_gate import QualityGate
from pipeline.readability_editor import polish


@dataclass
class Result:
    markdown_path: Path
    docx_path: Path | None
    sections: int
    resumed: int


def generate(
    brief_dict: dict,
    job_dir: Path,
    llm: LLMClient | None = None,
    make_docx: bool = True,
) -> Result:
    """Generate a document from a brief into ``job_dir``, resumable on crash."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    llm = llm or client_from_env()
    brief = Brief.from_dict(brief_dict)
    gate = QualityGate(llm)

    state = checkpoints.read_state(job_dir)
    done: list[dict] = list(state.get("sections", []))
    done_names = {s["section"] for s in done}
    resumed = len(done)

    tracker = ContextTracker()
    tracker.restore(done)

    for section in brief.sections:
        if section in done_names:  # (1) idempotent resume
            continue

        prior = tracker.prior_context()
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

    return Result(
        markdown_path=md_path,
        docx_path=docx_path,
        sections=len(done),
        resumed=resumed,
    )
