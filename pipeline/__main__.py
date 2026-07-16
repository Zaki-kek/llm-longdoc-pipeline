"""CLI: ``python -m pipeline <brief.yaml> --out <dir>``.

Defaults to the deterministic mock backend, so a fresh checkout produces a
document with no API key and no network. Set ``LLM_PROVIDERS`` to use a real
provider (see ``llm_client.client_from_env``).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.orchestrator import generate


def _load_brief(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # optional dependency

            return yaml.safe_load(text)
        except ImportError:
            raise SystemExit("PyYAML is required for .yaml briefs (pip install pyyaml)")
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("brief", type=Path, help="brief file (.yaml or .json)")
    parser.add_argument("--out", type=Path, default=Path("out"), help="output job directory")
    parser.add_argument("--no-docx", action="store_true", help="skip .docx export")
    args = parser.parse_args(argv)

    result = generate(_load_brief(args.brief), args.out, make_docx=not args.no_docx)
    print(
        f"Generated {result.sections} sections "
        f"(resumed {result.resumed}) -> {result.markdown_path}"
        + (f", {result.docx_path}" if result.docx_path else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
