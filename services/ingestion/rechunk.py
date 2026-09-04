"""
services.ingestion.rechunk — split oversized legacy units into retrievable chunks.

**The problem, measured.** The 43 English records are whole textbook units with a
median of 7,900 characters and a maximum of 9,595 — roughly 1,300 tokens each.
Retrieving one returns an entire unit to answer a question about one paragraph
in it, which wastes context and buries the relevant sentence among a thousand
irrelevant ones. The other two corpora do not have this problem: ICT sits at a
median of 1,767 characters and Physics at 1,560, both already inside the target
band, so **this module only splits what is actually too big**. Re-chunking a
record that is already the right size would churn identity for no gain.

**Target.** 400–600 tokens with 50 tokens of overlap, split at real boundaries,
per `docs/INGESTION_DESIGN.md` §5.

**Boundaries.** Splitting mid-sentence to hit an exact token count produces
chunks that begin halfway through a clause and embed badly. This splits at
paragraph breaks first and sentence ends second, and only falls back to a hard
word-boundary cut when a single sentence is itself longer than the window.

**Overlap** exists so a passage spanning a boundary is retrievable from either
side. It is measured in tokens and taken from the end of the previous chunk at a
sentence boundary where one is available, so the overlap is readable text rather
than a truncated fragment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .canonical import count_tokens

TARGET_TOKENS = 500
MIN_TOKENS = 400
MAX_TOKENS = 600
OVERLAP_TOKENS = 50

# Below this, a trailing piece is a stub rather than a short chunk, and is folded
# back into its predecessor. Above it, a short final piece is simply what dividing
# text into windows produces and is left alone — see the note in `split_text`.
STUB_TOKENS = 150

# A blank line, or a bullet the cleaning stage restored. Both are real structure.
_PARAGRAPH = re.compile(r"\n\s*\n|\n(?=•\s)")

# Sentence end: terminator, closing quote/bracket optional, then whitespace.
# Bengali danda (।) included — the ICT corpus needs it even though ICT records
# are rarely large enough to reach this code.
_SENTENCE_END = re.compile(r"(?<=[.!?।])[\"')\]]*\s+")


@dataclass(frozen=True)
class Piece:
    """One re-chunked span, and where it came from in the original."""

    text: str
    ordinal: int
    token_count: int
    char_start: int
    char_end: int
    # The piece's own content, without the overlap prefix carried from the
    # previous piece. Kept so the tail can be rebalanced without duplicating the
    # overlap into the result.
    body: str = ""

    @property
    def is_whole(self) -> bool:
        """True when the source was small enough to pass through untouched."""
        return self.ordinal == 0 and self.char_start == 0


def _segments(text: str) -> list[str]:
    """Break into the smallest units this module will not split further."""
    out: list[str] = []
    for para in _PARAGRAPH.split(text):
        para = para.strip()
        if not para:
            continue
        sentences = [s for s in _SENTENCE_END.split(para) if s.strip()]
        out.extend(sentences or [para])
    return out


def _tail_for_overlap(text: str, language: str, budget: int = OVERLAP_TOKENS) -> str:
    """
    Take up to `budget` tokens from the end of `text`, preferring whole sentences.

    Falls back to whole words. Never returns a fragment starting mid-word, which
    would embed as noise and could not be read by a human checking a citation.
    """
    if budget <= 0 or not text:
        return ""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    taken: list[str] = []
    for sentence in reversed(sentences):
        candidate = [sentence, *taken]
        if count_tokens(" ".join(candidate), language) > budget and taken:
            break
        taken = candidate

    tail = " ".join(taken).strip() if taken else text
    # The sentence loop always keeps at least one sentence, so a text with no
    # sentence boundary at all comes back whole. Left there, the "overlap" would
    # be the entire previous piece and every chunk would double in size. Trim by
    # words whenever the sentence-shaped tail is still over budget.
    if count_tokens(tail, language) > budget:
        words = tail.split()
        while words and count_tokens(" ".join(words), language) > budget:
            words.pop(0)
        tail = " ".join(words)
    return tail.strip()


def _hard_split(segment: str, language: str) -> list[str]:
    """Last resort for a single sentence longer than the window: cut on words."""
    # Cut short of the ceiling so the overlap prefix still fits afterwards.
    budget = MAX_TOKENS - OVERLAP_TOKENS
    words = segment.split()
    out, current = [], []
    for word in words:
        current.append(word)
        if count_tokens(" ".join(current), language) >= budget:
            out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return out


def split_text(text: str, *, language: str = "en") -> list[Piece]:
    """
    Split `text` into 400–600-token pieces with 50-token overlap.

    Returns a single whole piece when the text already fits, so a record that
    does not need splitting keeps one chunk and one identity.
    """
    text = text.strip()
    if not text:
        return []

    total = count_tokens(text, language)
    if total <= MAX_TOKENS:
        return [Piece(text=text, ordinal=0, token_count=total,
                      char_start=0, char_end=len(text))]

    segments: list[str] = []
    for segment in _segments(text):
        if count_tokens(segment, language) > MAX_TOKENS:
            segments.extend(_hard_split(segment, language))
        else:
            segments.append(segment)

    pieces: list[Piece] = []
    current: list[str] = []
    carried = ""
    cursor = 0

    def flush() -> None:
        nonlocal current, carried, cursor
        if not current:
            return
        body = " ".join(current).strip()
        if not body:
            current = []
            return
        # Overlap is a nicety; the ceiling is not. A body that already fills the
        # window leaves no room to prepend the previous tail, so the tail is
        # trimmed — and dropped entirely if even that will not fit. Letting it
        # through would put a chunk over the embedding window, which is the one
        # limit downstream cannot absorb.
        prefix = carried
        while prefix and count_tokens(f"{prefix} {body}", language) > MAX_TOKENS:
            words = prefix.split()[1:]
            prefix = " ".join(words)
        whole = f"{prefix} {body}".strip() if prefix else body
        start = text.find(current[0][:40], cursor)
        start = start if start >= 0 else cursor
        end = min(len(text), start + len(body))
        pieces.append(Piece(text=whole, ordinal=len(pieces),
                            token_count=count_tokens(whole, language),
                            char_start=start, char_end=end, body=body))
        cursor = max(cursor, end)
        carried = _tail_for_overlap(body, language)
        current = []

    for segment in segments:
        trial = " ".join([*current, segment]).strip()
        prospective = f"{carried} {trial}".strip() if carried else trial
        if current and count_tokens(prospective, language) > MAX_TOKENS:
            flush()
        current.append(segment)

    flush()

    # A trailing stub carries almost no retrievable signal and dilutes the
    # ranking pool, so the last two pieces are rebalanced rather than left as a
    # full chunk followed by a fragment.
    #
    # Merging was the obvious fix and does not work: a ~590-token piece plus a
    # 30-token tail is 620, over the ceiling, so the merge is refused and the
    # stub survives. On the real corpus that left 34 chunks under 150 tokens.
    # Splitting their combined content evenly instead gives two pieces of
    # roughly 310 tokens — both retrievable, neither over the window.
    #
    # Only a *stub* is worth this. The last piece of any division is short more
    # often than not, and a piece cannot be both above MIN_TOKENS and below
    # MAX_TOKENS once the remainder falls between them. The floor is advisory
    # for the final piece; the ceiling is absolute.
    if len(pieces) > 1 and pieces[-1].token_count < STUB_TOKENS:
        pieces = _rebalance_tail(pieces, text, language)

    return pieces


def _rebalance_tail(pieces: list[Piece], text: str, language: str) -> list[Piece]:
    """Even out the final two pieces when the last one is a stub."""
    last, prev = pieces[-1], pieces[-2]
    combined = f"{prev.body} {last.body}".strip()

    if count_tokens(combined, language) <= MAX_TOKENS:
        return pieces[:-2] + [Piece(
            text=combined, ordinal=prev.ordinal,
            token_count=count_tokens(combined, language),
            char_start=prev.char_start, char_end=last.char_end, body=combined)]

    units = [s for s in _SENTENCE_END.split(combined) if s.strip()] or combined.split()
    if len(units) < 2:
        return pieces

    half = count_tokens(combined, language) // 2
    head: list[str] = []
    for unit in units:
        if head and count_tokens(" ".join([*head, unit]), language) > half:
            break
        head.append(unit)
    tail_units = units[len(head):]
    if not head or not tail_units:
        return pieces

    head_text = " ".join(head).strip()
    tail_text = " ".join(tail_units).strip()
    overlap = _tail_for_overlap(head_text, language)
    tail_whole = f"{overlap} {tail_text}".strip() if overlap else tail_text
    if count_tokens(tail_whole, language) > MAX_TOKENS:
        tail_whole = tail_text

    return pieces[:-2] + [
        Piece(text=head_text, ordinal=prev.ordinal,
              token_count=count_tokens(head_text, language),
              char_start=prev.char_start, char_end=prev.char_end, body=head_text),
        Piece(text=tail_whole, ordinal=prev.ordinal + 1,
              token_count=count_tokens(tail_whole, language),
              char_start=prev.char_end, char_end=last.char_end, body=tail_text),
    ]


def needs_split(text: str, *, language: str = "en") -> bool:
    """Whether `split_text` would produce more than one piece."""
    return count_tokens(text.strip(), language) > MAX_TOKENS
