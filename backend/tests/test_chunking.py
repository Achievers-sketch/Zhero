"""Chunking tests: provenance, sections, overlap, cleaning."""

import pytest

from app.rag.chunking import chunk_pages, clean_pages, is_heading
from app.rag.parsing import ParsedPage


def pages(*texts: str) -> list[ParsedPage]:
    return [ParsedPage(i + 1, t) for i, t in enumerate(texts)]


def test_heading_detection() -> None:
    assert is_heading("1.2 Cooling subsystem")
    assert is_heading("3 POWER SUPPLY")
    assert is_heading("COOLING AND VENTILATION")
    assert is_heading("## Fan speed")
    assert not is_heading("1. Connect the unit to a suitable mains supply.")
    assert not is_heading("WARNING: Do not use a damaged cable.")
    assert not is_heading("WARNING")
    assert not is_heading("This is a normal sentence about the fan.")
    assert not is_heading("")


def test_chunks_carry_page_range_and_section() -> None:
    drafts = chunk_pages(
        pages(
            "1 INTRODUCTION\nIntro text on page one.",
            "More intro on page two.\n\n2 COOLING\nFan text on page two.",
            "Fan text continues on page three.",
        ),
        chunk_size=500,
        overlap=50,
    )
    assert [d.section for d in drafts] == ["1 INTRODUCTION", "2 COOLING"]
    assert (drafts[0].page_start, drafts[0].page_end) == (1, 2)
    assert (drafts[1].page_start, drafts[1].page_end) == (2, 3)
    assert [d.index for d in drafts] == [0, 1]


def test_chunks_never_span_sections() -> None:
    drafts = chunk_pages(
        [ParsedPage(None, "A HEAD\nalpha beta\n\nB HEAD\ngamma delta")], chunk_size=900, overlap=100
    )
    assert len(drafts) == 2
    assert "gamma" not in drafts[0].text and "alpha" not in drafts[1].text
    assert all(d.page_start is None and d.page_end is None for d in drafts)


def test_size_limit_and_overlap_use_whole_paragraphs() -> None:
    paragraphs = [f"Paragraph {i} " + "word " * 12 for i in range(10)]  # ~72 chars each
    drafts = chunk_pages([ParsedPage(None, "\n\n".join(paragraphs))], chunk_size=200, overlap=80)
    assert len(drafts) > 3
    assert all(len(d.text) <= 200 for d in drafts)
    # The first paragraph of a chunk repeats the last paragraph of the previous one.
    first_chunk_last = drafts[0].text.split("\n\n")[-1]
    assert drafts[1].text.split("\n\n")[0] == first_chunk_last


def test_overlap_keeps_exact_page_provenance() -> None:
    drafts = chunk_pages(
        pages("Alpha " * 25, "Beta " * 25, "Gamma " * 25), chunk_size=200, overlap=170
    )
    for d in drafts:
        body = d.text
        expected = {n for n, word in ((1, "Alpha"), (2, "Beta"), (3, "Gamma")) if word in body}
        assert d.page_start == min(expected) and d.page_end == max(expected)


def test_oversized_paragraph_is_windowed_with_overlap() -> None:
    long = " ".join(f"w{i}" for i in range(400))  # one paragraph, no breaks
    drafts = chunk_pages([ParsedPage(3, long)], chunk_size=300, overlap=60)
    assert len(drafts) > 3
    assert all(len(d.text) <= 300 for d in drafts)
    assert all(d.page_start == d.page_end == 3 for d in drafts)
    joined = " ".join(d.text for d in drafts)
    assert all(f"w{i} " in joined + " " for i in (0, 199, 399))
    # consecutive windows overlap
    assert set(drafts[0].text.split()[-3:]) & set(drafts[1].text.split())


def test_warning_paragraph_stays_whole() -> None:
    warning = (
        "WARNING: Disconnect mains power before opening the unit.\nDo not touch internal parts."
    )
    drafts = chunk_pages(
        [ParsedPage(None, f"intro\n\n{warning}\n\noutro")], chunk_size=900, overlap=100
    )
    assert warning in drafts[0].text


def test_empty_input_gives_no_chunks() -> None:
    assert chunk_pages([ParsedPage(1, "   \n\n  ")], chunk_size=900, overlap=100) == []
    assert chunk_pages([], chunk_size=900, overlap=100) == []


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        chunk_pages(pages("x"), chunk_size=100, overlap=100)


def test_clean_pages_removes_running_headers_footers_and_page_numbers() -> None:
    raw = [
        ParsedPage(n, f"ZH-DEMO Service Manual\nBody text for page {n} about cooling.\nPage {n}")
        for n in range(1, 6)
    ]
    cleaned = clean_pages(raw)
    for page in cleaned:
        assert "ZH-DEMO Service Manual" not in page.text
        assert f"Page {page.number}" not in page.text
        assert f"Body text for page {page.number} about cooling." in page.text


def test_clean_pages_keeps_repeated_warnings_and_body_lines() -> None:
    raw = [
        ParsedPage(n, f"Header\nWARNING: Disconnect power.\nUnique body {n}\nFooter text")
        for n in range(1, 6)
    ]
    for page in clean_pages(raw):
        assert "WARNING: Disconnect power." in page.text
        assert f"Unique body {page.number}" in page.text


def test_clean_pages_leaves_plain_text_alone() -> None:
    text = "1\nA short list\n2"
    assert clean_pages([ParsedPage(None, text)])[0].text == text


def test_clean_pages_removes_digit_varying_page_markers_but_keeps_numbered_body_lines() -> None:
    raw = [
        ParsedPage(
            n,
            f"Intro line {n}\nService Manual Rev 3 - Page {n} of 9\n"
            f"Body about step {n} of the test.",
        )
        for n in range(1, 6)
    ]
    for page in clean_pages(raw):
        assert "Service Manual Rev 3" not in page.text
        assert f"Intro line {page.number}" in page.text
        assert f"Body about step {page.number} of the test." in page.text
