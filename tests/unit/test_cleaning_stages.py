"""
Every cleaning stage, tested on its own.

The LUMOS-004C acceptance criterion is that each cleaning rule is a separate,
reversible stage with its own test. These are those tests. Fixtures are short
synthetic strings and a handful of real words whose correct spelling is a matter
of public fact — no licensed source text reaches this file.
"""

from __future__ import annotations

import pytest

from services.ingestion.cleaning import (
    STAGE_NAMES,
    clean,
    learn_true_compounds,
    normalise_whitespace,
    repair_bangla_doubled_consonant,
    repair_bullet_glyph,
    repair_hyphenated_line_break,
)


# ── Bangla: consonant doubled before a pre-base vowel sign ───────────────────

@pytest.mark.parametrize("damaged,expected", [
    ("ককোননো", "কোনো"),          # 364 occurrences in the ICT corpus
    ("যযোগাযযোগ", "যোগাযোগ"),    # 124
    ("হললো", "হলো"),              # 43
    ("মততো", "মতো"),              # 28
    ("ছছোটটো", "ছোটো"),          # 34 — two doublings in one word
    ("ববোতামে", "বোতামে"),
    ("মননোভাব", "মনোভাব"),
])
def test_doubled_consonant_before_vowel_is_repaired(damaged, expected):
    assert repair_bangla_doubled_consonant(damaged)[0] == expected


def test_repair_reports_how_many_times_it_fired():
    _, n = repair_bangla_doubled_consonant("ককোননো এবং যযোগাযযোগ")
    assert n == 4, "two doublings in each of two words"


def test_undamaged_bangla_is_left_alone():
    """The repaired spellings must be fixed points, or a second run corrupts them."""
    for clean_text in ("কোনো", "যোগাযোগ", "হলো", "তথ্য ও যোগাযোগ প্রযুক্তি"):
        assert repair_bangla_doubled_consonant(clean_text) == (clean_text, 0)


def test_repair_is_idempotent():
    once, _ = repair_bangla_doubled_consonant("ককোননো যযোগাযযোগ")
    twice, n = repair_bangla_doubled_consonant(once)
    assert twice == once and n == 0


def test_a_true_conjunct_geminate_is_not_touched():
    """
    Bengali writes a real doubled consonant as a conjunct with a virama.

    `ক্কো` is ক + ্ + ক + ো — the virama between the consonants means this is a
    legitimate geminate, not the extraction fault. The stage must leave it alone,
    which is the whole reason the pattern requires two *bare* consonants.
    """
    conjunct = "ক্কো"
    assert repair_bangla_doubled_consonant(conjunct) == (conjunct, 0)


def test_bangla_stage_does_not_run_on_english_text():
    """Language gating is the guard against silently corrupting the wrong corpus."""
    english = "the doorbell rang"
    assert clean(english, language="en").text == english
    assert "bangla_doubled_consonant" not in clean(english, language="en").changes


def test_unknown_language_runs_no_language_specific_stage():
    result = clean("ককোননো", language="unknown")
    assert "bangla_doubled_consonant" not in result.changes
    assert result.text == "ককোননো", "guessing the language could corrupt it"


# ── Bullet extracted as a lowercase 'e' ─────────────────────────────────────

def test_a_run_of_lone_es_is_restored_as_a_bullet_list():
    text, n = repair_bullet_glyph(
        "we will be able to e narrate incidents e participate in talks")
    assert n == 2
    assert text == "we will be able to\n• narrate incidents\n• participate in talks"


def test_a_single_lone_e_is_left_alone_as_ambiguous():
    """
    "the letter e is a vowel" is ordinary prose, and one `e` cannot be told from
    a bullet by reading the sentence. Repetition is what distinguishes them.
    """
    assert repair_bullet_glyph("we will be able to e narrate incidents")[1] == 0


def test_bullet_repair_leaves_real_words_alone():
    for safe in ("the letter e is a vowel", "e.g. this one", "we need coffee now"):
        assert repair_bullet_glyph(safe)[1] == 0, safe


def test_bullet_repair_needs_lowercase_on_both_sides():
    """`E` mid-sentence or a following capital is likelier to be real text."""
    assert repair_bullet_glyph("section E Narrate the story")[1] == 0


# ── Hyphenation across a lost line break ────────────────────────────────────

@pytest.mark.parametrize("damaged,expected", [
    ("prac- tise", "practise"),
    ("domi- nated", "dominated"),
    ("comme- moration", "commemoration"),
    ("over- crowded", "overcrowded"),
    ("begin- ning", "beginning"),
])
def test_split_words_are_rejoined(damaged, expected):
    assert repair_hyphenated_line_break(damaged)[0] == expected


def test_a_known_compound_keeps_its_hyphen():
    """
    `multi- religious` must not weld shut into `multireligious`.

    The corpus supplies the evidence: the same sentence writes `multi-racial`
    with no space, so `multi` is a prefix that keeps its hyphen here.
    """
    compounds = learn_true_compounds(["Sri Lanka is multi-racial and multi-lingual"])
    assert "multi" in compounds
    text, n = repair_hyphenated_line_break("a multi- religious country", compounds)
    assert (text, n) == ("a multi-religious country", 1)


def test_without_corpus_evidence_the_default_is_to_join():
    """Line-break hyphenation is the far more common cause, so it is the default."""
    assert repair_hyphenated_line_break("multi- religious")[0] == "multireligious"


def test_learning_ignores_a_hyphen_that_has_a_space():
    """`prac- tise` is damage, so `prac` must not be learned as a compound prefix."""
    assert "prac" not in learn_true_compounds(["I prac- tise daily"])


def test_bengali_dash_punctuation_is_not_treated_as_a_split_word():
    """
    `যেমন- সূর্যগ্রহণ` means "for example - solar eclipse".

    The dash is punctuation introducing a list, and `ই- লার্নিং` is "e-learning".
    The corpus auditor's `\\b\\w+-\\s+\\w+\\b` matched 75 of these in ICT and
    reported them as broken words; they are correct Bengali. This stage requires
    Latin letters on both sides for exactly that reason.
    """
    for bengali in ("যেমন- সূর্যগ্রহণ", "ই- লার্নিং", "অথেন্টিকেশন- এর"):
        assert repair_hyphenated_line_break(bengali)[1] == 0, bengali


# ── Whitespace ──────────────────────────────────────────────────────────────

def test_whitespace_runs_are_collapsed_and_lines_trimmed():
    text, n = normalise_whitespace("a    b   \nc \n\n\n\nd")
    assert text == "a b\nc\n\nd"
    assert n > 0


# ── Composition ─────────────────────────────────────────────────────────────

def test_stage_order_is_fixed():
    """
    Order is load-bearing, so it is asserted rather than assumed.

    Bangla repair must precede anything measuring length, since it removes 2,212
    characters from the ICT corpus. Whitespace must run last, because every other
    stage measures positions in the text it was handed.
    """
    assert STAGE_NAMES == (
        "bangla_doubled_consonant",
        "bullet_glyph_e",
        "hyphenated_line_break",
        "whitespace",
    )


def test_clean_reports_each_stage_separately():
    result = clean("ককোননো  যযোগাযযোগ", language="bn")
    assert result.changes["bangla_doubled_consonant"] == 4
    assert result.changed and result.total_changes >= 4
    assert result.original == "ককোননো  যযোগাযযোগ", "the input must survive"


def test_clean_on_undamaged_text_reports_no_change():
    result = clean("A clean English sentence.", language="en")
    assert not result.changed and result.changes == {}


def test_cleaning_the_output_again_changes_nothing():
    """Idempotency over the whole pipeline, not just one stage."""
    once = clean("ককোননো  যযোগাযযোগ", language="bn")
    twice = clean(once.text, language="bn")
    assert twice.text == once.text and not twice.changed
