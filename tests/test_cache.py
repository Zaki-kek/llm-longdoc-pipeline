import json

from pipeline.cache import CachingClient, FileCache, messages_fingerprint
from pipeline.llm_client import LLMClient, Message
from pipeline.mock_llm import MockLLM


class _CountingClient:
    name = "counting"

    def __init__(self):
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return "r"


def test_fingerprint_stable_and_content_sensitive():
    a = messages_fingerprint([Message("user", "a")])
    assert a == messages_fingerprint([Message("user", "a")])
    assert a != messages_fingerprint([Message("user", "b")])


def test_caching_dedups_calls():
    inner = _CountingClient()
    c = CachingClient(inner)
    msgs = [Message("user", "hello")]
    r1 = c.complete(msgs)
    r2 = c.complete(msgs)
    assert inner.calls == 1
    assert r1 == "r" and r2 == "r"


def test_filecache_persists_across_instances(tmp_path):
    path = tmp_path / "cache.json"
    a = FileCache(path)
    a["k"] = "v"
    b = FileCache(path)
    assert b["k"] == "v"
    with open(path) as fh:
        assert json.load(fh) == {"k": "v"}


def test_caching_client_satisfies_protocol():
    assert isinstance(CachingClient(MockLLM()), LLMClient) is True
