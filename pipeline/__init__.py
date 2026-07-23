from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from pipeline.api import RunConfig, run
from pipeline.orchestrator import Result

try:
    __version__ = version("llm-longdoc-pipeline")
except PackageNotFoundError:  # not installed (e.g. running from a source tree)
    __version__ = "0.1.0"

__all__ = ["run", "RunConfig", "Result", "__version__"]
