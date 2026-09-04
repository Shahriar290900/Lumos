"""
services.ingestion.mark_scheme — Edexcel mark schemes into canonical chunks.

**Two strategies, because one does not cover the paper.** Structured questions
end with `Total for question N`, and that terminator appears 9 / 8 / 4 times
across WPH11/12/13 — against 19 / 18 / 4 questions in the papers. The gap is
Section A: multiple-choice answers live in a table with no terminator at all.

    8   The correct answer is A (The ball bearing is moving downwards when
        the student starts the stopwatch)
        B is incorrect because time would be greater giving a lower value

The distractor explanations are the reason to bother. "B is incorrect
because…" is the most directly pedagogical text in the entire corpus — it says
why a wrong answer is wrong, which is what a student who chose B actually needs.
Discarding it as table noise would throw away the best teaching content here.

Mark schemes have a clean text layer on every page, so **no OCR is involved**.
`pdfplumber` reads them directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .canonical import CanonicalChunk
from .cleaning import clean

# Terminator for a structured question's block.
#
# The real text is `Total for question 11 5` — question number, then mark total,
# separated by whitespace. No "marks" word, no parentheses, no equals sign. The
# question papers write `(Total for Question 11 = 5 marks)`; the mark schemes do
# not, and a pattern carried over from the papers matches nothing. Measured: 0
# structured answers found across all three papers before this was corrected.
QUESTION_TOTAL = re.compile(
    r"Total\s+for\s+question\s+(\d{1,2})\s+(\d{1,2})\b", re.IGNORECASE)

# The Section A answer sentence. Deliberately not anchored to a question number
# on the same line: when the answer contains a formula the row breaks, and
# `1 𝟏𝟖𝟎 1` sits on its own line above `The correct answer is A ( )`. Anchoring
# to the number found 7 of 19 MCQs; anchoring to the sentence finds them all.
#
# Two phrasings, because WPH11 and WPH12 disagree — same board, same session,
# same month. WPH11 writes "The correct answer is A"; WPH12 writes "B is the
# correct answer". Supporting only the first found 19/19 in WPH11 and 0/10 in
# WPH12. This is the same lesson the examiner reports taught: a per-corpus
# assumption is wrong even within one session, so the parser has to be told what
# each document actually says rather than what the board's house style suggests.
MCQ_ANSWER = re.compile(
    r"(?:The\s+correct\s+answer\s+is\s+([A-D])|([A-D])\s+is\s+the\s+correct\s+answer)\b",
    re.IGNORECASE)

# A line that opens a numbered row.
ROW_START = re.compile(r"^\s*(\d{1,2})\s")

# "B is incorrect because ..." — one distractor explanation.
# "B is incorrect because…" (WPH11) and "A is not correct because…" (WPH12).
DISTRACTOR = re.compile(
    r"\b([A-D])\s+is\s+(?:incorrect|not\s+correct)\b", re.IGNORECASE)

# Page furniture that carries no answer content.
_NOISE = re.compile(
    r"^\s*(?:Pearson Education Limited.*|.*Registered Office.*|"
    r"Publications Code.*|All the material.*|Question\s+Answer\s+Mark|"
    r"Number|Mark|\d+|)\s*$", re.IGNORECASE)


@dataclass
class MarkSchemeAnswer:
    """One question's mark scheme, however it was found."""

    question_number: str
    text: str
    marks: int | None = None
    strategy: str = "terminator"          # or "mcq_table"
    mcq_answer: str | None = None
    distractors: list[str] = field(default_factory=list)
    page_number: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "question_number": self.question_number,
            "marks": self.marks,
            "strategy": self.strategy,
            "mcq_answer": self.mcq_answer,
            "distractor_count": len(self.distractors),
            "page_number": self.page_number,
            "characters": len(self.text),
        }


def clean_mark_scheme_text(raw: str) -> str:
    """Drop page furniture and column headers; keep everything that answers."""
    kept = [line.rstrip() for line in raw.split("\n") if not _NOISE.match(line)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def parse_structured(pages: Sequence[tuple[int, str]]) -> list[MarkSchemeAnswer]:
    """
    Terminator-bounded blocks, the same anchor the question papers use.

    A block runs from the end of the previous terminator to the end of this one,
    which is why the terminator is matched rather than the question opening: the
    opening is a bare number and far too ambiguous to anchor on.
    """
    joined, spans = [], []
    offset = 0
    for number, text in pages:
        joined.append(text)
        spans.append((offset, offset + len(text), number))
        offset += len(text) + 1
    body = "\n".join(joined)

    out: list[MarkSchemeAnswer] = []
    start = 0
    for match in QUESTION_TOTAL.finditer(body):
        block = body[start:match.start()]
        question = match.group(1)
        marks = int(match.group(2)) if match.group(2) else None
        text = clean_mark_scheme_text(block)
        if text:
            page = next((n for lo, hi, n in spans if lo <= match.start() < hi), None)
            out.append(MarkSchemeAnswer(question_number=question, text=text,
                                        marks=marks, strategy="terminator",
                                        page_number=page))
        start = match.end()
    return out


def parse_mcq_rows(pages: Sequence[tuple[int, str]],
                   already_found: set[str]) -> list[MarkSchemeAnswer]:
    """
    Section A, which the terminator never covers.

    Found by the answer sentence, not by table geometry. `extract_tables` on
    these PDFs splits a wrapped explanation across cells and loses the sentence,
    and the sentence is the content: "B is incorrect because 60 kW is the wasted
    energy" is the best teaching text in the corpus.

    The question number is carried forward from the last numbered row rather than
    required on the answer's own line, because a formula in the answer pushes the
    sentence onto the next line.
    """
    out: list[MarkSchemeAnswer] = []
    for page_number, text in pages:
        lines = text.split("\n")
        current: str | None = None
        for index, line in enumerate(lines):
            row = ROW_START.match(line)
            if row:
                current = row.group(1)
            match = MCQ_ANSWER.search(line)
            if not match or current is None or current in already_found:
                continue
            if any(a.question_number == current for a in out):
                continue

            block = [line.strip()]
            for following in lines[index + 1:]:
                if MCQ_ANSWER.search(following) or QUESTION_TOTAL.search(following):
                    break
                if ROW_START.match(following) and not DISTRACTOR.search(following):
                    break
                if following.strip():
                    block.append(following.strip())
            body = clean_mark_scheme_text("\n".join(block))
            if not body:
                continue
            out.append(MarkSchemeAnswer(
                question_number=current, text=body, marks=1,
                strategy="mcq_table",
                mcq_answer=(match.group(1) or match.group(2)).upper(),
                distractors=sorted({m.group(1).upper() for m in DISTRACTOR.finditer(body)}),
                page_number=page_number))
    return out


def parse_mark_scheme(pages: Sequence[tuple[int, str]]) -> list[MarkSchemeAnswer]:
    """Both strategies, structured first, MCQ filling the gap it leaves."""
    structured = parse_structured(pages)
    seen = {a.question_number for a in structured}
    answers = structured + parse_mcq_rows(pages, seen)
    return sorted(answers, key=lambda a: (int(a.question_number), a.strategy))


def answers_to_chunks(answers: Iterable[MarkSchemeAnswer], *, source_document_id: str,
                      offering_id: str, document_sha256: str,
                      paper_code: str | None = None) -> list[CanonicalChunk]:
    """One chunk per question's mark scheme, linked by (paper_code, question)."""
    chunks: list[CanonicalChunk] = []
    for ordinal, answer in enumerate(answers):
        cleaned = clean(answer.text, language="en")
        note = [f"Mark scheme, parsed by the {answer.strategy} strategy."]
        if answer.mcq_answer:
            note.append(f"Correct option: {answer.mcq_answer}.")
        if answer.distractors:
            note.append(f"Explains why {', '.join(answer.distractors)} "
                        f"{'is' if len(answer.distractors) == 1 else 'are'} incorrect.")
        chunks.append(CanonicalChunk(
            source_document_id=source_document_id,
            offering_id=offering_id,
            document_sha256=document_sha256,
            locator=f"ms/{answer.question_number}",
            text=cleaned.text,
            chunk_type="mark_scheme_answer",
            extraction_method="pdf_text_layer",
            provenance_status="cleaned",
            text_raw=answer.text,
            ordinal=ordinal,
            page_number=answer.page_number,
            question_number=answer.question_number,
            marks=answer.marks,
            language="en",
            notes=" ".join(note),
        ))
    return chunks
