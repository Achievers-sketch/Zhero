"""Stage 2 (SPLIT): clean text and split it into traceable chunks.

Every chunk records the page range and section heading it came from. Chunks never span
a section change, paragraphs (warnings, numbered steps) are kept whole where they fit,
and overlap is made of whole paragraphs so page provenance stays exact.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.rag.parsing import ParsedPage

_WARNING_WORDS = ("warning", "caution", "danger", "notice", "note")
_PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")
_DOTTED_HEADING = re.compile(r"^\d+(\.\d+)+\.?\s+\S")  # 1.2 Cooling system
_CAPS_NUMBERED_HEADING = re.compile(r"^\d+\.?\s+[A-Z][A-Z0-9 /&-]{2,}$")  # 3 POWER SUPPLY
_PAGE_MARKER = re.compile(
    r"(?:\bpage\s*\d+(?:\s*(?:of|/)\s*\d+)?\s*$)|(?:^\s*page\s*\d+\b)|(?:\b\d+\s*(?:of|/)\s*\d+\s*$)",
    re.IGNORECASE,
)
_EDGE_LINES = 3  # header/footer candidates: first/last N non-empty lines of a page


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    page_start: int | None
    page_end: int | None
    section: str | None
    text: str


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int | None
    section: str | None
    windowed: bool  # hard-split piece of an oversized paragraph; becomes its own chunk


def _starts_with_warning_word(line: str) -> bool:
    first = re.split(r"\W+", line.strip().lower(), maxsplit=1)[0]
    return first in _WARNING_WORDS


def is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80 or stripped.endswith((".", ",", ";", ":")):
        return stripped.startswith("#") and bool(_MARKDOWN_HEADING.match(stripped))
    if _starts_with_warning_word(stripped):
        return False
    if _MARKDOWN_HEADING.match(stripped) or _DOTTED_HEADING.match(stripped):
        return True
    if _CAPS_NUMBERED_HEADING.match(stripped):
        return True
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _heading_text(line: str) -> str:
    return line.strip().lstrip("#").strip()


def _exact(line: str) -> str:
    return " ".join(line.split()).lower()


def _digit_norm(line: str) -> str:
    return re.sub(r"\d+", "#", _exact(line))


def _edge_indexes(lines: list[str]) -> set[int]:
    non_empty = [i for i, line in enumerate(lines) if line.strip()]
    return set(non_empty[:_EDGE_LINES]) | set(non_empty[-_EDGE_LINES:])


def clean_pages(pages: list[ParsedPage]) -> list[ParsedPage]:
    """Drop repeated running headers/footers and bare page numbers at page edges.

    Only the first/last few lines of a page are candidates. A line is removed when it is
    (a) a bare page number, (b) identical on most pages, or (c) a "Page N"-style marker
    that repeats once its digits are ignored. Lines that merely differ by a number
    (e.g. body text) are kept, and lines starting with a warning word are never removed.
    """
    if all(page.number is None for page in pages):
        return pages  # plain text has no running headers/footers

    split = [page.text.splitlines() for page in pages]
    exact_counts: Counter[str] = Counter()
    marker_counts: Counter[str] = Counter()
    for lines in split:
        edges = [lines[i] for i in _edge_indexes(lines)]
        exact_counts.update({_exact(line) for line in edges})
        marker_counts.update({_digit_norm(line) for line in edges if _PAGE_MARKER.search(line)})
    threshold = max(3, math.ceil(0.6 * len(pages)))
    repeated_exact = {k for k, c in exact_counts.items() if c >= threshold}
    repeated_markers = {k for k, c in marker_counts.items() if c >= threshold}

    cleaned: list[ParsedPage] = []
    for page, lines in zip(pages, split, strict=True):
        edges = _edge_indexes(lines)
        kept: list[str] = []
        for i, line in enumerate(lines):
            if i in edges and line.strip() and not _starts_with_warning_word(line):
                stripped = line.strip()
                if (
                    _PAGE_NUMBER.match(stripped)
                    or (len(stripped) <= 80 and _exact(line) in repeated_exact)
                    or (
                        len(stripped) <= 80
                        and _PAGE_MARKER.search(stripped)
                        and _digit_norm(line) in repeated_markers
                    )
                ):
                    continue
            kept.append(line)
        cleaned.append(ParsedPage(page.number, "\n".join(kept)))
    return cleaned


def _window(text: str, size: int, overlap: int) -> list[str]:
    """Split oversized text into overlapping windows on word boundaries."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = max(
                text.rfind(" ", start + size // 2, end), text.rfind("\n", start + size // 2, end)
            )
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        nxt = text.find(" ", start, end)
        if nxt != -1:
            start = nxt + 1
    return pieces


def _build_units(pages: list[ParsedPage], size: int, overlap: int) -> list[_Unit]:
    units: list[_Unit] = []
    section: str | None = None

    def emit(buffer: list[str], page: int | None) -> None:
        text = "\n".join(buffer).strip()
        if not text:
            return
        if len(text) <= size:
            units.append(_Unit(text, page, section, False))
        else:
            units.extend(
                _Unit(piece, page, section, True) for piece in _window(text, size, overlap)
            )

    for page in pages:
        buffer: list[str] = []
        for raw in [*page.text.splitlines(), ""]:  # sentinel flushes the last paragraph
            line = raw.rstrip()
            if not line.strip():
                emit(buffer, page.number)
                buffer = []
            elif is_heading(line):
                emit(buffer, page.number)
                buffer = []
                section = _heading_text(line)
            else:
                buffer.append(line)
    return units


def _joined_len(units: list[_Unit]) -> int:
    return sum(len(u.text) for u in units) + 2 * max(0, len(units) - 1)


def _tail_overlap(units: list[_Unit], overlap: int) -> list[_Unit]:
    carried: list[_Unit] = []
    for unit in reversed(units):
        if _joined_len([unit, *carried]) > overlap:
            break
        carried.insert(0, unit)
    return carried


def _make(index: int, units: list[_Unit]) -> ChunkDraft:
    pages = [u.page for u in units if u.page is not None]
    return ChunkDraft(
        index=index,
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        section=units[0].section,
        text="\n\n".join(u.text for u in units),
    )


def chunk_pages(pages: list[ParsedPage], *, chunk_size: int, overlap: int) -> list[ChunkDraft]:
    """Split cleaned pages into chunks of at most ~``chunk_size`` characters."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    drafts: list[ChunkDraft] = []
    current: list[_Unit] = []

    def flush() -> None:
        if current:
            drafts.append(_make(len(drafts), current))

    for unit in _build_units(pages, chunk_size, overlap):
        if unit.windowed:
            flush()
            current = []
            drafts.append(_make(len(drafts), [unit]))
            continue
        if current and unit.section != current[0].section:
            flush()
            current = []
        if current and _joined_len([*current, unit]) > chunk_size:
            flush()
            current = _tail_overlap(current, overlap)
            if _joined_len([*current, unit]) > chunk_size:
                current = []
        current.append(unit)
    flush()
    return drafts
