"""Stage 1 (LOAD): extract text from supported documents, preserving PDF page numbers.

Uses pypdf (BSD licensed, pure Python). Encrypted, malformed and image-only PDFs are
detected and reported with clear codes instead of failing silently.
"""

import io
from dataclasses import dataclass, field

import pypdf

PARSER_VERSION = f"zhero-parse-1; pypdf-{pypdf.__version__}"
MAX_PDF_PAGES = 2000  # guard against pathological files


class ParseError(Exception):
    """A document could not be parsed; ``code`` is stable and safe to show to clients."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedPage:
    number: int | None  # 1-based for PDFs; None for plain text (no pages)
    text: str


@dataclass
class ParseResult:
    pages: list[ParsedPage]
    warnings: list[str] = field(default_factory=list)
    page_count: int | None = None


def parse_txt(data: bytes) -> ParseResult:
    if b"\x00" in data:
        raise ParseError("invalid_text", "File contains binary data and is not plain text.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("invalid_text", "File is not valid UTF-8 text.") from exc
    return ParseResult(pages=[ParsedPage(None, text)])


def parse_pdf(data: bytes) -> ParseResult:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
        # Owner-password-only PDFs open with an empty user password (as in any PDF viewer);
        # files that need a real password are reported instead of silently failing.
        if reader.is_encrypted and reader.decrypt("") == pypdf.PasswordType.NOT_DECRYPTED:
            raise ParseError(
                "encrypted_pdf", "The PDF is password-protected; upload an unprotected copy."
            )
        page_total = len(reader.pages)
    except ParseError:
        raise
    except Exception as exc:  # pypdf raises several unrelated error types for bad files
        raise ParseError("malformed_pdf", "The PDF could not be read; it may be corrupt.") from exc

    if page_total == 0:
        raise ParseError("malformed_pdf", "The PDF contains no pages.")
    if page_total > MAX_PDF_PAGES:
        raise ParseError("too_many_pages", f"The PDF has more than {MAX_PDF_PAGES} pages.")

    pages: list[ParsedPage] = []
    warnings: list[str] = []
    for index in range(page_total):
        number = index + 1
        try:
            text = reader.pages[index].extract_text() or ""
        except Exception:  # one bad page must not lose the whole document
            warnings.append(f"Page {number}: text extraction failed.")
            text = ""
        if not text.strip():
            warnings.append(
                f"Page {number}: no extractable text (blank or image-only; OCR is not supported)."
            )
        pages.append(ParsedPage(number, text))
    return ParseResult(pages=pages, warnings=warnings, page_count=page_total)
