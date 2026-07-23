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
import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable
from urllib.parse import urlsplit

from pipeline._logging import get_pipeline_logger
from pipeline.metrics import Metrics

logger = get_pipeline_logger(logger_name="pipeline.llm")


@dataclass(frozen=True)
class Message:
    """One chat turn. ``role`` is 'system' | 'user' | 'assistant'."""

    role: str
    content: str


class LLMError(RuntimeError):
    """Raised when a provider call ultimately fails (after retries)."""


def _is_private_host(host: str) -> bool:
    """True if ``host`` is loopback / link-local / RFC1918 private."""
    if host in ("localhost", "0.0.0.0", "::1"):
        return True
    if host.startswith("127.") or host.startswith("169.254.") or host.startswith("10."):
        return True
    if host.startswith("192.168."):
        return True
    if host.startswith("172."):
        parts = host.split(".")
        try:
            second = int(parts[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def validate_base_url(url: str) -> str:
    """Validate an LLM base URL against SSRF, returning it unchanged if safe.

    Requires an http/https scheme and a non-empty host. By default rejects
    loopback, link-local (incl. the cloud metadata address 169.254.169.254)
    and RFC1918 private hosts; set ``ALLOW_PRIVATE_LLM_URL=1`` to permit a
    private gateway. Raises ``LLMError`` naming the URL on a violation.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise LLMError(f"unsupported URL scheme in base_url: {url!r}")
    host = parts.hostname  # auto-lowercased, port stripped
    if not host:
        raise LLMError(f"missing host in base_url: {url!r}")
    if _is_private_host(host) and os.environ.get("ALLOW_PRIVATE_LLM_URL") != "1":
        raise LLMError(
            f"refusing private/loopback base_url {url!r}; "
            f"set ALLOW_PRIVATE_LLM_URL=1 to allow a private gateway"
        )
    return url


@runtime_checkable
class LLMClient(Protocol):
    """The only contract the pipeline depends on."""

    name: str

    def complete(self, messages: Sequence[Message]) -> str:
        """Return the assistant completion for ``messages``."""
        ...


@dataclass
class RetryPolicy:
    """Exponential backoff with a hard attempt cap.

    With ``jitter=False`` (default) ``delay_for`` returns the exact capped
    exponential backoff. With ``jitter=True`` it returns an equal-jitter delay
    uniformly in ``[0, cap]``; passing a seeded ``rng`` makes that path
    deterministic (useful in tests) while staying bounded by the same cap.
    """

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: bool = False

    def delay_for(self, attempt: int, rng: random.Random | None = None) -> float:
        cap = min(self.base_delay * (2 ** attempt), self.max_delay)
        return (rng or random).uniform(0, cap) if self.jitter else cap


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
    metrics: Metrics | None = None

    def complete(self, messages: Sequence[Message]) -> str:
        validate_base_url(self.base_url)  # SSRF guard first: before key check / any socket
        import requests  # local import keeps the module importable without the dep

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise LLMError(f"{self.name}: env var {self.api_key_env} is not set")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        url = self.base_url.rstrip("/") + "/chat/completions"

        metrics = self.metrics
        t0 = time.perf_counter()
        last_err: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            if metrics is not None:
                metrics.inc("llm.attempts")
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                if metrics is not None:
                    metrics.observe("llm.latency_seconds", time.perf_counter() - t0)
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001 - provider errors are opaque; we retry then wrap
                last_err = e
                if metrics is not None:
                    metrics.inc("llm.errors")
                if attempt + 1 < self.retry.max_attempts:
                    time.sleep(self.retry.delay_for(attempt))
        if metrics is not None:
            metrics.observe("llm.latency_seconds", time.perf_counter() - t0)
        logger.info(
            f"http.failed provider={self.name} attempts={self.retry.max_attempts} error={last_err}"
        )
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
    metrics: Metrics | None = None

    def complete(self, messages: Sequence[Message]) -> str:
        failures: list[tuple[str, str]] = []
        for client in self.clients:
            provider = getattr(client, "name", "?")
            try:
                return client.complete(messages)
            except LLMError as e:
                failures.append((provider, str(e)))
                if self.metrics is not None:
                    self.metrics.inc("llm.fallback.provider_failed")
                logger.info(f"fallback.provider_failed provider={provider} error={e}")
        if self.metrics is not None:
            self.metrics.inc("llm.fallback.exhausted")
        logger.info(f"fallback.exhausted providers={len(self.clients)}")
        detail = " | ".join(f"{n}: {r}" for n, r in failures)
        raise LLMError("all providers failed: " + detail)


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
