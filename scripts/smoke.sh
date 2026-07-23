#!/usr/bin/env bash
# Smoke test: run the quickstart on the deterministic mock backend.
# No API key, no network. Produces out/output.md and exits non-zero on failure.
set -euo pipefail

OUT_DIR="${1:-out}"
BRIEF="${2:-examples/report_from_brief/brief.yaml}"

python -m pipeline "$BRIEF" --out "$OUT_DIR" --no-docx

test -f "$OUT_DIR/output.md"
echo "smoke: OK -> $OUT_DIR/output.md"
