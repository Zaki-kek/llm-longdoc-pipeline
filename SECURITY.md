# Security Policy

This document describes the threat model of `llm-longdoc-pipeline` and the
hygiene the project follows. The pipeline is a library plus CLI that drives
third-party LLM endpoints and public bibliographic APIs; it does not run a
network server of its own.

## Secrets hygiene

- API keys and endpoints are read from environment variables only. No secret
  is ever committed to the repository, baked into a container image, or logged.
- `.env` files are git-ignored; `.env.example` ships placeholder values only.
- The provider layer (`pipeline/llm_client.py`) resolves each key from a named
  env var (`<PROVIDER>_API_KEY`) at call time, never from source.

## Threat model

- **Server-Side Request Forgery (SSRF) against the LLM endpoint.** The base URL
  of a provider is operator-supplied. A hostile or mistyped URL pointing at a
  loopback / link-local / RFC1918 address (for example the cloud metadata
  endpoint `169.254.169.254`) could exfiltrate credentials or reach internal
  services. `validate_base_url()` runs as the first statement of the HTTP
  client's `complete()` and rejects such hosts before any socket is opened.
- **SSRF against bibliographic APIs.** Citation verification calls public
  CrossRef / Semantic Scholar endpoints. Those URLs are fixed in code and are
  not operator-controlled, limiting the surface.
- **Do-not-trust LLM output.** Generated text is written into `.docx` and
  Markdown. It is treated as untrusted content: the pipeline does not execute
  it, and downstream consumers should not either.

## The `ALLOW_PRIVATE_LLM_URL` opt-in

Some deployments front their model behind a private gateway (a sidecar, an
internal load balancer, or `localhost` during development). For those cases the
SSRF guard can be relaxed by setting `ALLOW_PRIVATE_LLM_URL=1`. This is opt-in
and off by default, so the safe posture holds unless an operator deliberately
allows a private target. See
[`docs/decisions/0004-provider-agnostic-llm.md`](docs/decisions/0004-provider-agnostic-llm.md)
for the provider-layer design this guard sits in front of.

## Reporting a vulnerability

Please report suspected vulnerabilities through the repository's private
security advisory channel (GitHub Security Advisories) rather than a public
issue, and allow a reasonable window for a coordinated fix before disclosure.
