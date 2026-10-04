"""Local, bounded document extraction; no OCR or external services."""
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


MAX_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 15
MAX_CHARACTERS = 200_000
MIN_USEFUL_CHARACTERS = 200


@dataclass
class ExtractResult:
    text: str
    pages: int
    needs_manual_review: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _bounded_join(parts: list[str], separator: str = "\n") -> tuple[str, bool]:
    text = separator.join(parts)
    if len(text) <= MAX_CHARACTERS:
        return text, False
    return text[:MAX_CHARACTERS], True


def extract_text(data: bytes, filename: str) -> ExtractResult:
    """Extract PDF, DOCX or UTF-8 text under strict resource bounds."""
    if len(data) > MAX_BYTES:
        raise ValueError("CV exceeds the 5 MB limit")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise ValueError("Supported CV formats: PDF, DOCX, TXT")

    warnings: list[str] = []
    pages = 0
    parts: list[str] = []
    truncated = False
    try:
        if suffix == ".pdf":
            reader = PdfReader(BytesIO(data), strict=False)
            if reader.is_encrypted:
                try:
                    unlocked = reader.decrypt("")
                except Exception:
                    unlocked = 0
                if not unlocked:
                    return ExtractResult("", 0, True, ["Password-protected PDF"])
            pages = len(reader.pages)
            if pages > MAX_PDF_PAGES:
                warnings.append(f"PDF limited to the first {MAX_PDF_PAGES} pages")
            sparse_pages = 0
            for index in range(min(pages, MAX_PDF_PAGES)):
                try:
                    content = reader.pages[index].extract_text() or ""
                except Exception as exc:
                    content = ""
                    warnings.append(f"Page {index + 1} extraction failed: {type(exc).__name__}")
                if len(content.strip()) < 40:
                    sparse_pages += 1
                parts.append(content)
                if sum(map(len, parts)) >= MAX_CHARACTERS:
                    truncated = True
                    break
            if sparse_pages and sparse_pages == min(pages, MAX_PDF_PAGES):
                warnings.append("PDF pages have little extractable text; OCR may be required")
            text, clipped = _bounded_join(parts, "\n\f\n")
            truncated = truncated or clipped or pages > MAX_PDF_PAGES
        elif suffix == ".docx":
            document = Document(BytesIO(data))
            for block in document.element.body.iterchildren():
                if block.tag.endswith("}p"):
                    parts.append(Paragraph(block, document).text)
                elif block.tag.endswith("}tbl"):
                    table = Table(block, document)
                    for row in table.rows:
                        # Keep cells on one source line so column structure is visible.
                        parts.append("   ".join(cell.text for cell in row.cells))
                if sum(map(len, parts)) >= MAX_CHARACTERS:
                    truncated = True
                    break
            text, clipped = _bounded_join(parts)
            truncated = truncated or clipped
            pages = 1  # DOCX is reflowable; no reliable page count without rendering.
            warnings.append("DOCX page count is an estimate")
        else:
            try:
                decoded = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                decoded = data.decode("utf-8-sig", errors="replace")
                warnings.append("TXT contained invalid UTF-8 bytes")
            pages = decoded.count("\f") + 1
            text = decoded[:MAX_CHARACTERS]
            truncated = len(decoded) > MAX_CHARACTERS
    except Exception as exc:
        return ExtractResult("", pages, True, [f"Extraction failed: {type(exc).__name__}"])

    if truncated:
        warnings.append(f"Extracted text capped at {MAX_CHARACTERS} characters")
    useful = len("".join(text.split()))
    short = useful < MIN_USEFUL_CHARACTERS
    if short:
        warnings.append("Fewer than 200 extracted non-whitespace characters; manual review required")
    needs_review = short or truncated or any("extraction failed" in warning.lower() for warning in warnings)
    return ExtractResult(text, pages, needs_review, warnings)
