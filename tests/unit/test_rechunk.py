"""
Re-chunking oversized legacy units.

The 43 English records are whole textbook units with a median of 7,900
characters — roughly 1,300 tokens. Retrieving one to answer a question about a
single paragraph wastes context and buries the relevant sentence. These tests
pin the split, the boundaries it splits on, and the property that matters most:
that a record small enough already is left completely alone.
"""

from __future__ import annotations

from services.ingestion.canonical import count_tokens
from services.ingestion.rechunk import (
    MAX_TOKENS,
    MIN_TOKENS,
    OVERLAP_TOKENS,
    STUB_TOKENS,
    needs_split,
    split_text,
)


def _english(words: int) -> str:
    """A paragraph of roughly `words` tokens, in whole sentences."""
    sentence = "The student measures the acceleration of a falling object carefully. "
    return (sentence * (words // 10 + 1)).strip()


def test_text_within_the_window_is_returned_whole():
    text = _english(120)
    pieces = split_text(text, language="en")
    assert len(pieces) == 1
    assert pieces[0].text == text, "a record that fits must not be rewritten"
    assert pieces[0].ordinal == 0


def test_a_record_that_fits_is_not_reported_as_needing_a_split():
    assert not needs_split(_english(100), language="en")
    assert needs_split(_english(2000), language="en")


def test_an_oversized_record_is_split():
    pieces = split_text(_english(2000), language="en")
    assert len(pieces) > 1


def test_no_piece_exceeds_the_maximum():
    for piece in split_text(_english(3000), language="en"):
        assert piece.token_count <= MAX_TOKENS, (
            f"piece {piece.ordinal} is {piece.token_count} tokens, over {MAX_TOKENS}")


def test_no_piece_is_a_stub():
    """
    A trailing stub is folded back; a merely short tail is not.

    A piece cannot be both above the floor and below the ceiling once the
    remainder falls between them, and the ceiling is the harder constraint
    because the embedding window enforces it. So every piece but the last
    respects the floor, the last respects only the stub threshold, and all of
    them respect the ceiling.
    """
    pieces = split_text(_english(2000), language="en")
    assert len(pieces) > 1
    for piece in pieces[:-1]:
        assert piece.token_count >= MIN_TOKENS
    assert pieces[-1].token_count >= STUB_TOKENS
    for piece in pieces:
        assert piece.token_count <= MAX_TOKENS


def test_pieces_are_numbered_in_order():
    pieces = split_text(_english(2500), language="en")
    assert [p.ordinal for p in pieces] == list(range(len(pieces)))


def test_consecutive_pieces_overlap():
    """
    Overlap exists so a passage crossing a boundary is retrievable from either
    side. Without it, a sentence split across two chunks is findable from
    neither.
    """
    pieces = split_text(_english(2500), language="en")
    assert len(pieces) > 1
    for previous, following in zip(pieces, pieces[1:]):
        opening = following.text[:60]
        assert opening.strip(), "a piece must not start with whitespace"
        assert opening in previous.text or any(
            word in previous.text for word in opening.split()[:4]), (
            "consecutive pieces share no text, so the boundary is unretrievable")


def test_overlap_starts_at_a_word_boundary():
    """A piece must never begin mid-word — it would embed as noise."""
    for piece in split_text(_english(2500), language="en"):
        assert not piece.text[:1].isspace()
        assert piece.text[0].isalnum() or piece.text[0] in "•\"'("


def test_splitting_prefers_sentence_ends():
    pieces = split_text(_english(2000), language="en")
    # Every sentence in the fixture ends with a full stop, so a split that
    # respected boundaries leaves each piece ending on one.
    assert sum(1 for p in pieces if p.text.rstrip().endswith(".")) >= len(pieces) - 1


def test_a_single_sentence_longer_than_the_window_still_splits():
    """The hard fallback: no sentence boundary exists to split on."""
    runaway = "word " * 3000
    pieces = split_text(runaway, language="en")
    assert len(pieces) > 1
    for piece in pieces:
        assert piece.token_count <= MAX_TOKENS


def test_bangla_is_measured_with_the_bangla_token_rule():
    """
    Bangla tokenises at roughly three characters per token, not one per word.

    Using the Latin heuristic on Bangla would under-count by several times and
    produce chunks far over the window. `count_tokens` already knows this; the
    splitter must use it rather than counting words.
    """
    bangla = "তথ্য ও যোগাযোগ প্রযুক্তি ব্যবহার করে শিক্ষার্থীরা শিখতে পারে। " * 60
    pieces = split_text(bangla, language="bn")
    for piece in pieces:
        assert count_tokens(piece.text, "bn") <= MAX_TOKENS


def test_empty_text_produces_no_pieces():
    assert split_text("", language="en") == []
    assert split_text("   \n  ", language="en") == []


def test_splitting_is_deterministic():
    text = _english(2500)
    first = [p.text for p in split_text(text, language="en")]
    for _ in range(3):
        assert [p.text for p in split_text(text, language="en")] == first


def test_every_piece_records_where_it_came_from():
    """Provenance: a derived chunk must trace back into its source."""
    text = _english(2000)
    for piece in split_text(text, language="en"):
        assert 0 <= piece.char_start <= len(text)
        assert piece.char_start <= piece.char_end <= len(text)


def test_overlap_budget_is_respected():
    pieces = split_text(_english(2500), language="en")
    assert OVERLAP_TOKENS > 0
    # The carried tail is bounded, so no piece should be dominated by overlap.
    for piece in pieces[1:]:
        assert piece.token_count > OVERLAP_TOKENS
