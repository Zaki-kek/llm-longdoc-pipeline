from pipeline.quality_gate import QualityGate, parse_judge


def test_parse_judge_ready():
    assert parse_judge("READY").ready


def test_parse_judge_needs_fixes():
    r = parse_judge("NEEDS_FIXES: missing data section")
    assert not r.ready
    assert "missing data" in r.reasons


def test_parse_judge_malformed_is_fail_open():
    # unknown format must not deadlock the pipeline -> treated as READY
    assert parse_judge("hmm, looks fine to me").ready


class _ScriptedLLM:
    name = "scripted"

    def __init__(self, replies):
        self._replies = list(replies)

    def complete(self, messages):
        return self._replies.pop(0)


def test_ensure_accepts_when_ready():
    gate = QualityGate(_ScriptedLLM(["READY"]))
    out = gate.ensure("Data", "draft-0", "topic", revise=lambda fb: "revised")
    assert out == "draft-0"


def test_ensure_revises_then_accepts():
    gate = QualityGate(_ScriptedLLM(["NEEDS_FIXES: thin", "READY"]), max_revisions=2)
    out = gate.ensure("Data", "draft-0", "topic", revise=lambda fb: "draft-1")
    assert out == "draft-1"


def test_ensure_stops_at_cap():
    gate = QualityGate(_ScriptedLLM(["NEEDS_FIXES: a", "NEEDS_FIXES: b"]), max_revisions=2)
    out = gate.ensure("Data", "d0", "topic", revise=lambda fb: "dX")
    assert out == "dX"  # returns latest draft after the cap, never loops forever
