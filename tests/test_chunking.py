import pytest

from pipeline.chunking import chunk_text, pack_context
from pipeline.mock_llm import MockLLM
from pipeline.orchestrator import generate

BRIEF = {"topic": "Test topic", "sections": ["Overview", "Analysis", "Data", "Conclusion"]}


def test_coverage_and_bound_no_overlap():
    text = ("Sentence one here. Another sentence follows.\n\n" * 45)
    chunks = chunk_text(text, 300, overlap=0)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks) == text


def test_overlap_reconstruct_invariant():
    text = ("Para content sentence. More content here.\n\n" * 45)
    max_chars = 300
    chunks = chunk_text(text, max_chars, overlap=20)
    assert all(len(c) <= max_chars for c in chunks)
    assert chunks[0] + "".join(c[20:] for c in chunks[1:]) == text


def test_short_text_single_chunk():
    assert chunk_text("abc", 300) == ["abc"]


def test_arg_validation():
    with pytest.raises(ValueError):
        chunk_text("x", 0)
    with pytest.raises(ValueError):
        chunk_text("x", 10, overlap=10)


def test_pack_context_keeps_latest_and_bounds():
    out = pack_context(["a", "b", "c", "ddddd"], 3)
    assert len(out) <= 3
    assert "d" in out
    assert "a" not in out


def test_orchestrator_default_unchanged(tmp_path):
    res = generate(BRIEF, tmp_path, llm=MockLLM(), make_docx=False)
    assert res.sections == 4
