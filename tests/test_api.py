import dataclasses

import pytest

import pipeline
from pipeline import Result, RunConfig, __version__, run
from pipeline.mock_llm import MockLLM

BRIEF = {"topic": "Test topic", "sections": ["Overview", "Analysis", "Data", "Conclusion"]}


def test_public_imports_and_version():
    assert isinstance(__version__, str) and __version__


def test_run_produces_result(tmp_path):
    res = run(BRIEF, tmp_path, llm=MockLLM(), config=RunConfig(make_docx=False))
    assert isinstance(res, Result)
    assert res.sections == 4
    assert res.resumed == 0
    assert res.markdown_path.exists()


def test_runconfig_is_frozen():
    cfg = RunConfig(make_docx=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.make_docx = False


def test_runconfig_validates_context_budget():
    with pytest.raises(ValueError):
        RunConfig(context_budget=0)


def test_public_all_surface():
    assert {"run", "RunConfig", "Result", "__version__"} <= set(pipeline.__all__)
