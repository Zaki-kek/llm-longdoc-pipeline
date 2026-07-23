import pytest

from pipeline.llm_client import HTTPChatClient, LLMError, Message, validate_base_url


def test_valid_public_url_passes():
    assert validate_base_url("https://api.example.com") == "https://api.example.com"


def test_bad_scheme_and_missing_host_raise():
    for bad in ("ftp://x", "", "http:///nohost"):
        with pytest.raises(LLMError):
            validate_base_url(bad)


def test_private_host_rejected_unless_opted_in(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_LLM_URL", raising=False)
    with pytest.raises(LLMError):
        validate_base_url("http://127.0.0.1:8000")
    monkeypatch.setenv("ALLOW_PRIVATE_LLM_URL", "1")
    assert validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    monkeypatch.delenv("ALLOW_PRIVATE_LLM_URL", raising=False)
    # 172.32 is OUTSIDE the private 172.16-172.31 range -> accepted
    assert validate_base_url("http://172.32.0.1") == "http://172.32.0.1"


def test_ssrf_guard_fires_before_socket(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_LLM_URL", raising=False)
    monkeypatch.setenv("X_API_KEY", "k")
    client = HTTPChatClient(
        name="x",
        model="m",
        base_url="http://169.254.169.254",
        api_key_env="X_API_KEY",
    )
    with pytest.raises(LLMError) as ei:
        client.complete([Message("user", "hi")])
    assert "169.254.169.254" in str(ei.value)
