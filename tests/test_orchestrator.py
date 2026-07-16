from pathlib import Path

from pipeline.orchestrator import generate
from pipeline.mock_llm import MockLLM
from pipeline import checkpoints as C

BRIEF = {"topic": "Test topic", "sections": ["Overview", "Analysis", "Data", "Conclusion"]}


def test_generate_smoke(tmp_path: Path):
    res = generate(BRIEF, tmp_path, llm=MockLLM(), make_docx=False)
    assert res.sections == 4 and res.resumed == 0
    assert res.markdown_path.exists()
    assert "## Analysis" in res.markdown_path.read_text()


def test_generate_resumes_from_checkpoint(tmp_path: Path):
    # pre-seed two completed sections (simulating a prior partial run)
    C.write_state(tmp_path, {
        "sections": [{"section": "Overview", "text": "x"}, {"section": "Analysis", "text": "y"}],
        "last_step": 2,
    })
    res = generate(BRIEF, tmp_path, llm=MockLLM(), make_docx=False)
    assert res.sections == 4
    assert res.resumed == 2  # the two done sections were not regenerated
