import threading

from pipeline.metrics import Metrics
from pipeline.mock_llm import MockLLM
from pipeline.orchestrator import generate
from pipeline.quality_gate import QualityGate

BRIEF = {"topic": "Test topic", "sections": ["Overview", "Analysis", "Data", "Conclusion"]}


class _ScriptedLLM:
    name = "scripted"

    def __init__(self, replies):
        self._replies = list(replies)

    def complete(self, messages):
        return self._replies.pop(0)


def test_counter_inc():
    m = Metrics()
    m.inc("x")
    m.inc("x", 2)
    assert m.snapshot()["counters"]["x"] == 3


def test_observe_timing():
    m = Metrics()
    m.observe("t", 0.01)
    s = m.snapshot()
    assert s["timings"]["t"]["count"] == 1
    assert s["timings"]["t"]["total"] >= 0


def test_lock_under_threads():
    m = Metrics()

    def worker():
        m.inc("c")

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.snapshot()["counters"]["c"] == 50


def test_gate_records_revisions():
    m = Metrics()
    gate = QualityGate(_ScriptedLLM(["NEEDS_FIXES: x", "READY"]), metrics=m)
    gate.ensure("Data", "d0", "topic", revise=lambda fb: "d1")
    assert m.snapshot()["counters"].get("gate.revisions", 0) >= 1


def test_orchestrator_surfaces_metrics(tmp_path):
    res = generate(BRIEF, tmp_path, llm=MockLLM(), make_docx=False)
    assert isinstance(res.metrics, dict)
    assert "counters" in res.metrics
