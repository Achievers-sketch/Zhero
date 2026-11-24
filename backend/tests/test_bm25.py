"""Lexical retrieval tests."""

from app.rag.bm25 import BM25Index, make_excerpt, tokenize


def test_tokenize_drops_stopwords_and_keeps_part_numbers() -> None:
    tokens = tokenize("What is the part number FAN-2040-X for the fan?")
    assert "fan-2040-x" in tokens and "2040" in tokens and "fan" in tokens
    assert "what" not in tokens and "the" not in tokens


def test_ranking_prefers_relevant_chunks() -> None:
    docs = [
        tokenize(t)
        for t in ["fan speed warning cooling", "probe cable connector", "mains power plug"]
    ]
    scores = BM25Index(docs).score(tokenize("fan speed"))
    assert scores[0] > 0 and scores[1] == 0 and scores[2] == 0


def test_exact_part_number_match_wins() -> None:
    docs = [
        tokenize(t) for t in ["replacement fan FAN-2040-X cooling", "fan cooling general fan fan"]
    ]
    scores = BM25Index(docs).score(tokenize("FAN-2040-X"))
    assert scores[0] > scores[1]


def test_no_match_scores_zero() -> None:
    scores = BM25Index([tokenize("alpha beta")]).score(tokenize("gamma"))
    assert scores == [0.0]


def test_empty_index_and_query() -> None:
    assert BM25Index([]).score(["x"]) == []
    assert BM25Index([["a"]]).score([]) == [0.0]


def test_excerpt_picks_best_matching_line_and_truncates() -> None:
    text = "Intro line.\nThe cooling fan runs slowly when blocked.\nUnrelated closing line."
    assert (
        make_excerpt(text, tokenize("cooling fan")) == "The cooling fan runs slowly when blocked."
    )
    long = "fan " * 200
    assert len(make_excerpt(long, ["fan"], max_chars=50)) <= 50
