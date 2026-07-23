import random

import pytest

from pipeline.llm_client import FallbackClient, LLMError, Message, RetryPolicy


class _AlwaysFail:
    def __init__(self, name):
        self.name = name

    def complete(self, messages):
        raise LLMError(f"{self.name} down")


class _AlwaysOk:
    name = "good"

    def complete(self, messages):
        return "ok"


def test_default_backoff_backward_compat():
    for attempt in range(6):
        assert RetryPolicy().delay_for(attempt) == min(0.5 * (2 ** attempt), 8.0)


def test_jitter_deterministic_and_bounded():
    p = RetryPolicy(jitter=True)
    for attempt in range(6):
        d = p.delay_for(attempt, rng=random.Random(0))
        assert 0.0 <= d <= min(0.5 * (2 ** attempt), 8.0)
    assert p.delay_for(2, rng=random.Random(0)) == p.delay_for(2, rng=random.Random(0))


def test_provider_names_surfaced():
    a = _AlwaysFail("alpha")
    b = _AlwaysFail("bravo")
    with pytest.raises(LLMError) as ei:
        FallbackClient([a, b]).complete([Message("user", "x")])
    assert "alpha" in str(ei.value)
    assert "bravo" in str(ei.value)


def test_fallback_success():
    bad = _AlwaysFail("bad")
    good = _AlwaysOk()
    assert FallbackClient([bad, good]).complete([Message("user", "x")]) == "ok"
