from pipeline.readability_editor import strip_filler


def test_strip_filler_removes_known_phrases():
    out = strip_filler("It is important to note that latency dropped.")
    assert "important to note" not in out.lower()
    assert "latency dropped" in out


def test_strip_filler_keeps_facts():
    text = "The system handles 100 requests per second."
    assert strip_filler(text) == text
