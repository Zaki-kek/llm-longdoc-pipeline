from pipeline.citation_verifier import (
    normalize_text,
    match_title,
    match_year,
    is_non_latin_source,
)


def test_normalize_text_lowercases_and_collapses_ws():
    assert normalize_text("  The   BIG  Short ") == normalize_text("the big short")
    assert normalize_text("HELLO world") == "hello world"


def test_match_title_fuzzy():
    assert match_title("Weapons of Math Destruction", "weapons of math destruction") > 0.95
    assert match_title("Weapons of Math Destruction", "A totally different book") < 0.5


def test_match_year_tolerant():
    assert match_year(2016, "2016")
    assert match_year(2016, 2017)  # within tolerance
    assert not match_year(2016, 1999)


def test_is_non_latin_source():
    # non-Latin scripts (Greek, CJK) are flagged as unverifiable-by-these-APIs
    assert is_non_latin_source({"title": "Θεωρία Πληροφορίας", "authors": ["Σάνον"]})
    assert is_non_latin_source({"title": "情報理論", "authors": ["田中"]})
    assert not is_non_latin_source({"title": "Information Theory", "authors": ["Shannon"]})
