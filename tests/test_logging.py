import json
import logging

from pipeline._logging import get_pipeline_logger, new_run_id
from pipeline.mock_llm import MockLLM
from pipeline.orchestrator import generate

BRIEF = {"topic": "Test topic", "sections": ["Overview", "Analysis", "Data", "Conclusion"]}


def test_new_run_id_unique():
    assert new_run_id()
    assert new_run_id() != new_run_id()


def test_schema_contract(caplog):
    caplog.set_level(logging.INFO, logger="pipeline")
    get_pipeline_logger(run_id="r1", stage="generate").info("x")
    payloads = [json.loads(r.getMessage()) for r in caplog.records]
    assert any(
        p.get("run_id") == "r1" and p.get("stage") == "generate" and "msg" in p
        for p in payloads
    )


def test_orchestrator_emits_structured_logs(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="pipeline")
    generate(BRIEF, tmp_path, llm=MockLLM(), make_docx=False)
    payloads = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.getMessage().startswith("{")
    ]
    assert any(p.get("run_id") for p in payloads)
    assert any(p.get("stage") == "generate" for p in payloads)
    assert any("section.done" in str(p.get("msg", "")) for p in payloads)
