"""
services.ingestion.ocr — rendering and OCR for documents with no text layer.

Two things need this. *Student Book 1* has **no text layer on any of its 225
pages**, and the WPH11 and WPH13 examiner reports embed subset fonts with no
`ToUnicode` CMap, so every extractor returns `(cid:N)` rather than characters —
pdfplumber, pypdf, pdfium and poppler alike. That is not recoverable by trying
another library, which is why this module exists.

**Page by page, with immediate cleanup.** 225 pages rendered at 250 DPI is
roughly 1–2 GB of PNG held at once, and the development machine had 1.4 GB free
when this was written. Each page is rendered, OCR'd, and released before the
next, so peak usage is one page.

**Confidence is recorded, never assumed.** Tesseract reports per-word
confidence; a page below the floor is marked `ocr_uncertain` (ADR-021) rather
than stored as though it were exact. An OCR pipeline that does not say how sure
it is produces text nobody can audit.

**Requires** `tesseract` on PATH and `pypdfium2` + `pytesseract` installed.
Neither is imported at module load, so the rest of the ingestion package still
imports on a machine without them.

    brew install tesseract          # macOS
    apt-get install tesseract-ocr   # Debian/Ubuntu
    pip install pypdfium2 pytesseract
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# 250 DPI was measured during reconnaissance as the point where Tesseract reads
# this textbook's prose cleanly. Higher costs time and memory for no gain on
# body text; lower loses the smaller sidebar type.
DEFAULT_DPI = 250

# Below this mean word confidence a page is `ocr_uncertain`. Not a quality bar
# for rejection — the text is still kept, because uncertain text a human can
# review beats no text at all.
CONFIDENCE_FLOOR = 70.0

# Specification references OCR badly: `1.3.1` comes back as `131` because the
# decimal points are lost in a small-font sidebar. These references are the link
# between a textbook section and an exam question, so they matter more than most
# text and get a second pass at higher DPI with a digit allowlist.
SPEC_REFERENCE = re.compile(r"\b(\d)\.(\d)\.(\d)\b")
SPEC_SQUASHED = re.compile(r"\b(\d{3})\b")

# Handwritten candidate scripts in examiner reports OCR to noise. The examiner's
# own commentary follows this marker and is the valuable part.
EXAMINER_COMMENT_MARKER = re.compile(r"Examiner\s+Comments?", re.IGNORECASE)
RESULTS_PLUS_MARKER = re.compile(r"Results\s*Plus", re.IGNORECASE)


class OcrUnavailable(RuntimeError):
    """Tesseract or a render library is missing. Says which, and how to fix it."""


@dataclass
class OcrPage:
    """One page's OCR result, with enough to judge whether to trust it."""

    page_number: int
    text: str
    confidence: float
    dpi: int = DEFAULT_DPI
    words: int = 0
    spec_references: list[str] = field(default_factory=list)

    @property
    def uncertain(self) -> bool:
        return self.confidence < CONFIDENCE_FLOOR

    @property
    def provenance_status(self) -> str:
        """`ocr_uncertain` below the floor, `derived` above it. Never `verbatim`."""
        return "ocr_uncertain" if self.uncertain else "derived"

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "confidence": round(self.confidence, 2),
            "uncertain": self.uncertain,
            "dpi": self.dpi,
            "words": self.words,
            "characters": len(self.text),
            "spec_references": self.spec_references,
        }


def _require() -> tuple[Any, Any]:
    """Import the OCR toolchain, or explain exactly what is missing."""
    try:
        import pypdfium2
        import pytesseract
    except ImportError as exc:
        raise OcrUnavailable(
            f"{exc.name} is not installed. Run: pip install pypdfium2 pytesseract"
        ) from None
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 - pytesseract raises several types
        raise OcrUnavailable(
            "the tesseract binary is not on PATH. Install it with "
            "`brew install tesseract` or `apt-get install tesseract-ocr`."
        ) from None
    return pypdfium2, pytesseract


def repair_spec_references(text: str) -> tuple[str, list[str]]:
    """
    Restore `1.3.1` from the `131` that OCR produces, and collect what is found.

    Only three-digit runs are considered, and only where each digit is a
    plausible specification component. A bare `131` in running prose could be a
    page number or a value, so this is reported alongside the repair rather than
    applied silently — the caller decides whether to trust it.
    """
    found = [f"{a}.{b}.{c}" for a, b, c in SPEC_REFERENCE.findall(text)]
    repaired = SPEC_SQUASHED.sub(
        lambda m: ".".join(m.group(1)) if m.group(1)[0] in "12345678" else m.group(1),
        text)
    found += [f"{a}.{b}.{c}" for a, b, c in SPEC_REFERENCE.findall(repaired)]
    return repaired, sorted(set(found))


def drop_candidate_scripts(text: str) -> tuple[str, int]:
    """
    Discard photographed handwriting, keep the examiner's commentary.

    Examiner reports interleave scanned candidate answers with "ResultsPlus /
    Examiner Comments" analysis. The handwriting OCRs to noise —
    `is is eo spite / Swe. 93% 1:08. +. XP 14 ¥f08 "= EO Bo` — while the prose
    after the marker explains *why* a mark was or was not awarded, which is the
    single strongest reason to keep examiner reports at all.

    Everything between a ResultsPlus marker and the following Examiner Comments
    marker is dropped. Returns the text and how many blocks were removed.
    """
    dropped = 0
    out: list[str] = []
    skipping = False
    for line in text.split("\n"):
        if RESULTS_PLUS_MARKER.search(line):
            skipping = True
            dropped += 1
            continue
        if skipping:
            if EXAMINER_COMMENT_MARKER.search(line):
                skipping = False
            continue
        out.append(line)
    return "\n".join(out).strip(), dropped


def ocr_pages(path: Path, *, dpi: int = DEFAULT_DPI, first: int = 1,
              last: int | None = None, language: str = "eng") -> Iterator[OcrPage]:
    """
    Render and OCR one page at a time, releasing each before the next.

    A generator on purpose: 225 pages at 250 DPI materialised together is 1–2 GB,
    and the machine this was written on had 1.4 GB free. Yielding lets the caller
    write each page and move on, so peak memory is one page regardless of how
    long the document is.
    """
    pdfium, pytesseract = _require()

    document = pdfium.PdfDocument(str(path))
    try:
        total = len(document)
        stop = min(last or total, total)
        for index in range(first - 1, stop):
            page = document[index]
            bitmap = page.render(scale=dpi / 72)
            image = bitmap.to_pil()
            try:
                data = pytesseract.image_to_data(
                    image, lang=language, output_type=pytesseract.Output.DICT)
                confidences = [float(c) for c in data.get("conf", [])
                               if str(c) not in ("-1", "")]
                text = pytesseract.image_to_string(image, lang=language)
                repaired, references = repair_spec_references(text)
                yield OcrPage(
                    page_number=index + 1,
                    text=repaired.strip(),
                    confidence=(sum(confidences) / len(confidences)) if confidences else 0.0,
                    dpi=dpi,
                    words=len([w for w in data.get("text", []) if str(w).strip()]),
                    spec_references=references,
                )
            finally:
                # Release the render before the next page. Without this the
                # generator holds every bitmap it has produced.
                image.close()
                del bitmap
                page.close()
    finally:
        document.close()
