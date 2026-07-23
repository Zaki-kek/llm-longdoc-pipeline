"""Structured JSON logging with contextual fields.

A ``LoggerAdapter`` wraps the standard logger and attaches a job_id + stage +
substep context to every record, emitting JSON so downstream tooling can
filter by job_id.

Usage:
    from pipeline._logging import get_pipeline_logger
    log = get_pipeline_logger(job_id=155, stage="draft", substep="section")
    log.info("started")  # -> {"job_id": 155, "stage": "draft", ..., "msg": "started"}
"""
import json
import logging
import uuid
from typing import Any, MutableMapping


class PipelineLoggerAdapter(logging.LoggerAdapter):
    """Prepends structured context to every log record."""

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        extra = dict(self.extra or {})
        payload = {**extra, "msg": msg}
        return json.dumps(payload, ensure_ascii=False), kwargs


def new_run_id() -> str:
    """Return a short, unique run identifier for correlating log records."""
    return uuid.uuid4().hex[:8]


def get_pipeline_logger(
    job_id: int | str | None = None,
    stage: str | None = None,
    substep: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    logger_name: str = "pipeline",
) -> PipelineLoggerAdapter:
    """Return a logger carrying structured context. All fields are optional."""
    base = logging.getLogger(logger_name)
    context: dict[str, Any] = {}
    if job_id is not None:
        context["job_id"] = job_id
    if stage:
        context["stage"] = stage
    if substep:
        context["substep"] = substep
    if session_id:
        context["session_id"] = session_id
    if run_id:
        context["run_id"] = run_id
    return PipelineLoggerAdapter(base, context)
