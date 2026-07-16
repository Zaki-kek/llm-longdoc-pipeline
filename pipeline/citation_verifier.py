"""Citation grounding: check that cited sources actually exist.

Given a list of citations (title / authors / year), each is looked up against
two public bibliographic APIs - CrossRef and Semantic Scholar - and accepted
only if a candidate matches on fuzzy title, author surnames and year. This
catches hallucinated references before a document ships.

Sources in a non-Latin script are skipped (marked ``unverifiable`` rather than
``not_found``): these public APIs index them poorly, so a miss there is not
evidence the source is fake.

Network access is lazy and rate-limited; the pure matching helpers
(``normalize_text``, ``match_title``, ``match_year``) are import- and
test-friendly with no network.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Optional

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
CROSSREF_BASE = "https://api.crossref.org"

TITLE_THRESHOLD = 0.82
AUTHOR_THRESHOLD = 0.5
YEAR_TOLERANCE = 1


# --- pure matching helpers (no network) ------------------------------------

def normalize_text(s: str) -> str:
    """Lowercase and collapse whitespace (punctuation preserved)."""
    return " ".join(str(s).lower().split())


def match_title(t1: str, t2: str) -> float:
    """Fuzzy title similarity in [0, 1]."""
    return SequenceMatcher(None, normalize_text(t1), normalize_text(t2)).ratio()


def _surname(author: str) -> str:
    """Best-effort surname token from a free-form author string."""
    cleaned = re.sub(r"[^\w\s.-]", "", str(author)).strip()
    parts = [p for p in re.split(r"[\s,]+", cleaned) if len(p) > 1 and "." not in p]
    if not parts:
        return normalize_text(cleaned)
    # the longest token is usually the surname
    return normalize_text(max(parts, key=len))


def match_authors(ours: list[str], api_authors: list[dict]) -> float:
    """Fraction of our author surnames found among API author names."""
    if not ours:
        return 1.0
    api_surnames = {_surname(a.get("name", "")) for a in api_authors}
    hits = sum(1 for a in ours if _surname(a) in api_surnames)
    return hits / len(ours)


def match_year(ours: Any, api: Any) -> bool:
    """Year match within a small tolerance; missing years are permissive."""
    try:
        return abs(int(ours) - int(api)) <= YEAR_TOLERANCE
    except (TypeError, ValueError):
        return True


def is_non_latin_source(citation: dict) -> bool:
    """True if the title or an author is written in a non-Latin script."""
    blob = str(citation.get("title", "")) + " ".join(
        str(a) for a in citation.get("authors", [])
    )
    for ch in blob:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            if name and "LATIN" not in name:
                return True
    return False


# --- network layer ----------------------------------------------------------

class RateLimiter:
    """Simple minimum-interval limiter between calls."""

    def __init__(self, calls_per_min: int) -> None:
        self._interval = 60.0 / max(1, calls_per_min)
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last = time.time()


@dataclass
class VerificationResult:
    title: str
    status: str  # "verified" | "not_found" | "unverifiable"
    source_api: str = ""
    score: float = 0.0


@dataclass
class _Client:
    base: str
    limiter: RateLimiter = field(default_factory=lambda: RateLimiter(30))
    timeout: float = 15.0

    def get(self, path: str, params: dict) -> Optional[dict]:
        import requests

        self.limiter.wait()
        try:
            resp = requests.get(self.base + path, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


def _score(citation: dict, cand_title: str, cand_authors: list[dict], cand_year: Any) -> float:
    if match_title(citation.get("title", ""), cand_title) < TITLE_THRESHOLD:
        return 0.0
    if match_authors(citation.get("authors", []), cand_authors) < AUTHOR_THRESHOLD:
        return 0.0
    if not match_year(citation.get("year"), cand_year):
        return 0.0
    return match_title(citation.get("title", ""), cand_title)


def verify_citation(citation: dict) -> VerificationResult:
    """Verify one citation against Semantic Scholar, then CrossRef."""
    title = str(citation.get("title", ""))
    if is_non_latin_source(citation):
        return VerificationResult(title, "unverifiable")

    s2 = _Client(SEMANTIC_SCHOLAR_BASE)
    data = s2.get("/paper/search", {"query": title, "fields": "title,authors,year", "limit": 5})
    for paper in (data or {}).get("data", []) or []:
        score = _score(citation, paper.get("title", ""), paper.get("authors", []), paper.get("year"))
        if score:
            return VerificationResult(title, "verified", "semantic_scholar", score)

    cr = _Client(CROSSREF_BASE)
    data = cr.get("/works", {"query.bibliographic": title, "rows": 5})
    for item in (data or {}).get("message", {}).get("items", []) or []:
        cand_title = (item.get("title") or [""])[0]
        authors = [{"name": f"{a.get('given', '')} {a.get('family', '')}"} for a in item.get("author", [])]
        year = (item.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0]
        score = _score(citation, cand_title, authors, year)
        if score:
            return VerificationResult(title, "verified", "crossref", score)

    return VerificationResult(title, "not_found")


def verify_citations_batch(citations: list[dict]) -> dict:
    """Verify a list of citations and return a summary + per-item results."""
    results = [verify_citation(c) for c in citations]
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"summary": counts, "results": [r.__dict__ for r in results]}
