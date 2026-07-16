"""Provider-agnostic LLM layer with fallback and bounded retries.

The pipeline never talks to a vendor SDK directly. It depends on the small
``LLMClient`` protocol below, so any backend - a hosted OpenAI-compatible
endpoint, a local model, or the deterministic mock used in CI - is a drop-in.

Design goals:
- No vendor lock-in: one ``complete(messages) -> str`` contract.
- Resilience: a ``FallbackClient`` tries providers in order, so a single
  provider outage degrades to the next instead of failing the whole run.
- Zero secrets in code: keys and endpoints come from environment variables.
- Testable offline: ``MockLLM`` (see ``mock_llm.py``) satisfies the same
  protocol, so the full pipeline runs in CI without a key or network.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class Message:
    """One chat turn. ``role`` is 'system' | 'user' | 'assistant'."""

    role: str
    content: str


class LLMError(RuntimeError):
    """Raised when a provider call ultimately fails (after retries)."""


@runtime_checkable
class LLMClient(Protocol):
    """The only contract the pipeline depends on."""

    name: str

    def complete(self, messages: Sequence[Message]) -> str:
        """Return the assistant completion for ``messages``."""
        ...


@dataclass
class RetryPolicy:
    """Exponential backoff with a hard attempt cap."""

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0

    def delay_for(self, attempt: int) -> float:
        return min(self.base_delay * (2 ** attempt), self.max_delay)


@dataclass
class HTTPChatClient:
    """Backend for any OpenAI-compatible ``/chat/completions`` endpoint.

    Provider, base URL, model and API key are read from the environment,
    so the same class serves a hosted API or a local server (e.g. an
    OpenAI-compatible gateway) with no code change and no secret in the repo.
    """

    name: str
    model: str
    base_url: str
    api_key_env: str
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: float = 60.0

    def complete(self, messages: Sequence[Message]) -> str:
        import requests  # local import keeps the module importable without the dep

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise LLMError(f"{self.name}: env var {self.api_key_env} is not set")

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        url = self.base_url.rstrip("/") + "/chat/completions"

        last_err: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001 - provider errors are opaque; we retry then wrap
                last_err = e
                if attempt + 1 < self.retry.max_attempts:
                    time.sleep(self.retry.delay_for(attempt))
        raise LLMError(f"{self.name}: failed after {self.retry.max_attempts} attempts: {last_err}")


@dataclass
class FallbackClient:
    """Try each client in order; return the first success.

    Turns N single-provider clients into one resilient client: a provider
    outage or rate-limit degrades to the next provider instead of failing
    the pipeline. Raises ``LLMError`` only if every provider fails.
    """

    clients: Sequence[LLMClient]
    name: str = "fallback"

    def complete(self, messages: Sequence[Message]) -> str:
        errors: list[str] = []
        for client in self.clients:
            try:
                return client.complete(messages)
            except LLMError as e:
                errors.append(str(e))
        raise LLMError("all providers failed: " + " | ".join(errors))


def client_from_env() -> LLMClient:
    """Build a client from ``LLM_PROVIDERS`` (comma-separated), newest first.

    Each name maps to env vars ``<NAME>_MODEL`` / ``<NAME>_BASE_URL`` /
    ``<NAME>_API_KEY``. Unset or ``mock`` yields the deterministic MockLLM,
    so a fresh checkout runs offline out of the box.
    """
    names = [n.strip() for n in os.environ.get("LLM_PROVIDERS", "mock").split(",") if n.strip()]
    clients: list[LLMClient] = []
    for name in names:
        if name == "mock":
            from pipeline.mock_llm import MockLLM

            clients.append(MockLLM())
            continue
        up = name.upper()
        clients.append(
            HTTPChatClient(
                name=name,
                model=os.environ.get(f"{up}_MODEL", "default"),
                base_url=os.environ.get(f"{up}_BASE_URL", ""),
                api_key_env=f"{up}_API_KEY",
            )
        )
    if not clients:
        from pipeline.mock_llm import MockLLM

        clients.append(MockLLM())
    return clients[0] if len(clients) == 1 else FallbackClient(clients)
