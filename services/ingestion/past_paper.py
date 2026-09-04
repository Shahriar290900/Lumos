"""
services.ingestion.past_paper — exam paper to canonical question chunks.

Implements the boundary rule verified during reconnaissance: in a Pearson Edexcel
IAL Physics paper, `(Total for Question N = M marks)` terminates every main
question. It was 19 of 19 in WPH11, and it carries the mark total, so boundary
detection and mark extraction come from a single match.

**One complete main question, with all its sub-parts, is one chunk.** That is the
whole multi-part mechanism. No explicit dependency cross-reference was found in
any audited AS paper — a scan for "your answer to", "answer to part", "value
calculated in", "use your" and related phrasings returned zero matches — so
`depends_on` has nothing to extract from and is never required for ingestion
(ADR-016). Keeping the parts together means the context needed to explain part
(c) is present whenever part (c) is retrieved, by construction rather than by
parsing.

Sub-parts are *detected and recorded* without splitting the chunk, so a client
can navigate to `(c)(ii)` and an evaluation set can address it, while retrieval
still returns the whole question.

The chunker is pure: it takes `(page_number, text)` pairs, not a file. PDF
extraction lives in `extract_pages()` and is the only part that needs a library,
which keeps the parsing logic testable against small synthetic fixtures rather
than against copyrighted material.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .canonical import CanonicalChunk

# The verified terminator. Also yields the mark total.
QUESTION_TERMINATOR = re.compile(
    r"\(\s*Total\s+for\s+Question\s+(\d+)\s*=\s*(\d+)\s*marks?\s*\)",
    re.IGNORECASE)

# Sub-part labels: (a) (b) (c) at the first level, (i) (ii) (iii) nested inside.
#
# `(i)`, `(v)` and `(x)` are both single letters and Roman numerals, so the label
# alone cannot decide the level. The rule below resolves it by position: a
# numeral-shaped label is nested only once a first-level part has opened, which
# is how these papers are actually laid out — (a) then (i), never (i) then (a).
SUB_PART = re.compile(r"^\s*\(([a-z])\)\s*(.*)$")
SUB_SUB_PART = re.compile(r"^\s*\((i{1,3}|iv|v|vi{1,3}|ix|x{1,3})\)\s*(.*)$")
AMBIGUOUS_LABELS = frozenset({"i", "v", "x"})
# A bare parenthesised integer on its own line is a per-part mark allocation.
PART_MARKS = re.compile(r"^\s*\((\d{1,2})\)\s*$")

# Layout noise verified in the extracted text of real papers. Removing it is
# recorded as a transformation (`provenance_status='cleaned'`), and the raw text
# is retained, so nothing here is a silent rewrite.
BOILERPLATE_LINES = frozenset({
    "do not write in this area",
    "d o not write in this area",
    "aera siht ni etirw ton od",     # the same text, mirrored by the extractor
    "turn over",
    "do", "not", "write", "in", "this", "area",   # the phrase, one word per line
    "d", "o",
})
PRINT_CODE = re.compile(r"^\s*\*?[A-Z]\d{5,}[A-Z]?\d*\*?\s*$")
DOT_LEADER = re.compile(r"\.{6,}")
BLANK_RUN = re.compile(r"\n{3,}")


@dataclass
class ParsedQuestion:
    """One main question, boundaries resolved, sub-parts recorded not split."""

    question_number: str
    marks: int
    text: str
    text_raw: str
    page_start: int | None
    page_end: int | None
    sub_parts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PaperParseReport:
    """Counts and structure only — never question text. Safe to write to disk."""

    questions_found: int = 0
    total_marks: int = 0
    numbering_gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sub_part_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "questions_found": self.questions_found,
            "total_marks": self.total_marks,
            "numbering_gaps": self.numbering_gaps,
            "warnings": self.warnings,
            "sub_part_counts": self.sub_part_counts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_paper_text(raw: str) -> str:
    """
    Strip layout furniture that would otherwise dominate the embedding.

    On a structured-question page the answer-line dot leaders alone can outweigh
    the question text, so any length or token measurement taken before this is
    simply wrong.

    Removes only furniture: margin boilerplate and its mirrored twin, print
    codes, "Turn over", standalone page numbers, and dot-leader runs. It never
    alters wording, and the caller keeps the raw text.
    """
    kept: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if stripped.lower() in BOILERPLATE_LINES:
            continue
        if PRINT_CODE.match(stripped):
            continue
        if stripped.isdigit() and len(stripped) <= 3:   # standalone page number
            continue
        line = DOT_LEADER.sub(" ", line).rstrip()
        if not line.strip():
            continue
        kept.append(line)
    return BLANK_RUN.sub("\n\n", "\n".join(kept)).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def _page_index(pages: Sequence[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Concatenate pages and return spans so an offset can be mapped to a page."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    for page_number, text in pages:
        text = text or ""
        parts.append(text)
        spans.append((cursor, page_number))
        cursor += len(text) + 1
    return "\n".join(parts), spans


def _page_for(offset: int, spans: list[tuple[int, int]]) -> int | None:
    page = None
    for start, number in spans:
        if start <= offset:
            page = number
        else:
            break
    return page


def detect_sub_parts(text: str) -> list[dict[str, Any]]:
    """
    Find the sub-part structure inside a question without splitting it.

    Marks are attached to the most recent label, because a bare `(3)` on its own
    line is the allocation for the part above it. The label is only anchored at
    the start of a line: a bare `(3)` is far too ambiguous to match anywhere else.
    """
    parts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_level_1: str | None = None

    for line in text.split("\n"):
        roman = SUB_SUB_PART.match(line)
        alpha = SUB_PART.match(line)

        # A Roman numeral is nested only when a first-level part is already open.
        # Without that guard `(i)` reads as the letter i and opens a bogus first
        # level, which then adopts `(ii)` as its child.
        is_nested = bool(roman) and (
            len(roman.group(1)) > 1
            or (roman.group(1) in AMBIGUOUS_LABELS and last_level_1 is not None)
        )

        if is_nested:
            label = f"{last_level_1 or ''}({roman.group(1)})"
            current = {"label": label, "level": 2, "marks": None}
            parts.append(current)
            continue

        if alpha:
            last_level_1 = f"({alpha.group(1)})"
            current = {"label": last_level_1, "level": 1, "marks": None}
            parts.append(current)
            continue

        m = PART_MARKS.match(line)
        if m and current is not None and current["marks"] is None:
            current["marks"] = int(m.group(1))
    return parts


def parse_questions(pages: Sequence[tuple[int, str]]
                    ) -> tuple[list[ParsedQuestion], PaperParseReport]:
    """
    Split a paper into main questions using the verified terminator.

    The terminator is the anchor and the opening question number is validation,
    not the other way round: the terminator is unambiguous, while a line starting
    with a digit is not.

    A gap in the question numbering is reported rather than ignored. Numbers run
    1..N continuously in these papers, so a gap means the parser lost a question
    — a failure that must reach the ingestion report, not disappear.
    """
    report = PaperParseReport()
    full, spans = _page_index(pages)

    questions: list[ParsedQuestion] = []
    cursor = 0
    for match in QUESTION_TERMINATOR.finditer(full):
        number, marks = match.group(1), int(match.group(2))
        raw_body = full[cursor:match.start()]
        cursor = match.end()

        body = clean_paper_text(raw_body)
        # Trim anything before this question's own opening number, so trailing
        # furniture from the previous question does not leak in.
        opening = re.search(rf"(?m)^\s*{re.escape(number)}\s+\S", body)
        if opening:
            body = body[opening.start():].strip()

        if not body:
            report.warnings.append(
                f"question {number}: no text between boundaries after cleaning")
            continue

        questions.append(ParsedQuestion(
            question_number=number,
            marks=marks,
            text=body,
            text_raw=raw_body,
            page_start=_page_for(match.start() - len(raw_body), spans),
            page_end=_page_for(match.start(), spans),
            sub_parts=detect_sub_parts(body),
        ))

    report.questions_found = len(questions)
    report.total_marks = sum(q.marks for q in questions)
    report.sub_part_counts = {q.question_number: len(q.sub_parts) for q in questions}

    numbers = [int(q.question_number) for q in questions]
    if numbers:
        expected = list(range(1, max(numbers) + 1))
        gaps = sorted(set(expected) - set(numbers))
        report.numbering_gaps = [str(n) for n in gaps]
        if gaps:
            report.warnings.append(
                f"question numbering is not contiguous; missing {gaps} — "
                "the parser lost a question, or the paper is not standard")
    return questions, report


# ─────────────────────────────────────────────────────────────────────────────
# Canonical conversion
# ─────────────────────────────────────────────────────────────────────────────

def questions_to_chunks(questions: Iterable[ParsedQuestion], *,
                        source_document_id: str, offering_id: str,
                        document_sha256: str, extraction_method: str,
                        language: str = "en") -> list[CanonicalChunk]:
    """
    Turn parsed questions into canonical chunks.

    `sub_question` is deliberately NULL: the chunk *is* the whole question, and
    claiming a sub-part identifier would misrepresent what was stored. The parts
    are in `sub_parts`.
    """
    chunks: list[CanonicalChunk] = []
    for ordinal, q in enumerate(questions):
        chunks.append(CanonicalChunk(
            source_document_id=source_document_id,
            offering_id=offering_id,
            document_sha256=document_sha256,
            locator=f"q/{q.question_number}",
            text=q.text,
            text_raw=q.text_raw,
            chunk_type="exam_question",
            extraction_method=extraction_method,
            # Furniture was removed, so this is not verbatim — and the raw text
            # is retained so the transformation can be inspected.
            provenance_status=(
                "ocr_uncertain" if extraction_method == "ocr_tesseract" else "cleaned"),
            ordinal=ordinal,
            page_number=q.page_start,
            page_number_end=q.page_end,
            question_number=q.question_number,
            sub_question=None,
            marks=q.marks,
            sub_parts=q.sub_parts,
            language=language,
            notes=(
                f"Complete main question with {len(q.sub_parts)} detected sub-part(s), "
                "kept together as one retrieval unit (ADR-016)."
            ),
        ))
    return chunks


def extract_pages(path: Path) -> list[tuple[int, str]]:
    """
    Read a PDF's text layer, page by page.

    The only part of this module that needs a library, and the only part that
    touches a file. Callers that already have text — tests, or an OCR pipeline —
    should call `parse_questions` directly.

    Returns pages verbatim; cleaning happens during parsing so the raw text
    survives into `text_raw`.
    """
    import pdfplumber  # imported lazily: parsing does not need it

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(str(path)) as doc:
        for index, page in enumerate(doc.pages, start=1):
            pages.append((index, page.extract_text() or ""))
    return pages
