# Multi-stage build: install into a clean runtime image, run as a non-root
# user. No secrets are baked in - provider keys are passed at run time via -e.

# --- builder: resolve and install the package + deps into a venv -----------
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_NO_CACHE_DIR=1

# Copy only what is needed to build the wheel first (better layer caching).
COPY pyproject.toml README.md LICENSE ./
COPY pipeline ./pipeline

# Install into an isolated virtualenv we can copy wholesale to the runtime.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir ".[docx,yaml]"

# --- runtime: minimal image with just the installed environment -----------
FROM python:3.12-slim AS runtime

# Non-root user for the running process.
RUN adduser --disabled-password --gecos '' appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
USER appuser

# Batch CLI: `docker run <image> <brief.yaml> --out <dir>`. No HEALTHCHECK
# (this is a one-shot job, not a long-lived server).
ENTRYPOINT ["python", "-m", "pipeline"]
