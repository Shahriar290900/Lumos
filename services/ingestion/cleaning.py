"""
services.ingestion.cleaning — reversible, individually measured cleaning stages.

Each defect the legacy corpus carries gets one stage. A stage is a pure function
over text that also reports how many times it fired, so a normalisation run can
say *what* it changed rather than only *that* it changed something. Stages are
composed in a fixed order and every one is independently testable, which is the
LUMOS-004C acceptance criterion: "every cleaning rule is a separate, reversible
stage with its own test".

**Reversible** here means the original survives, not that the transform has a
mathematical inverse. `CanonicalChunk` keeps `text_raw` for anything not
`verbatim` (ADR-021), and the database refuses a transformed chunk that has
dropped its input. So any stage can be re-run, re-measured or reasoned about
against the text it actually received.

Nothing in this module guesses. Every rule below was derived by measuring the
real corpus, and the measurements are recorded in the docstrings because the
numbers are the justification for the rule existing at all.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Bengali character classes
# ─────────────────────────────────────────────────────────────────────────────

# ক..হ, plus the three nukta-composed consonants and khanda-ta, which are single
# codepoints and so cannot be written as a range endpoint.
BENGALI_CONSONANTS = "ক-হৎড়ঢ়য়"

# The vowel signs that are *rendered* with a pre-base component. In Unicode
# these are single codepoints, but they decompose: ো is ে + া, and ৌ is ে + ৗ.
# That decomposition is the mechanism behind the corruption this module repairs.
PRE_BASE_VOWEL_SIGNS = "োেৌ"

_DOUBLED_BEFORE_VOWEL = re.compile(
    f"([{BENGALI_CONSONANTS}])\\1([{PRE_BASE_VOWEL_SIGNS}])")

# A lone lowercase `e` standing as its own word. See `repair_bullet_glyph`.
_LONE_E = re.compile(r"(?<=[a-z,;:]) e (?=[a-z])")

# `word- word`: a hyphen followed by a space, mid-sentence. Line-break
# hyphenation from the source PDF, with the newline lost during extraction.
_SPLIT_WORD = re.compile(r"\b([A-Za-z]{2,})-\s+([A-Za-z]{2,})\b")

# A real compound: hyphen with no space around it. Used to learn which prefixes
# legitimately keep their hyphen, so `multi- religious` is not welded shut.
_TRUE_COMPOUND = re.compile(r"\b([A-Za-z]{2,})-([A-Za-z]{2,})\b")


# ─────────────────────────────────────────────────────────────────────────────
# Stage plumbing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Stage:
    """One named repair. `apply` returns the new text and how many times it fired."""

    name: str
    description: str
    apply: Callable[..., tuple[str, int]]
    languages: frozenset[str] | None = None   # None = any language

    def applies_to(self, language: str) -> bool:
        return self.languages is None or language in self.languages


@dataclass
class CleaningResult:
    """What cleaning did, per stage. Counts are reported, never estimated."""

    text: str
    original: str
    changes: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.text != self.original

    @property
    def total_changes(self) -> int:
        return sum(self.changes.values())

    def as_dict(self) -> dict[str, object]:
        return {
            "changed": self.changed,
            "total_changes": self.total_changes,
            "by_stage": dict(self.changes),
        }


# ─────────────────────────────────────────────────────────────────────────────
# The stages
# ─────────────────────────────────────────────────────────────────────────────

def repair_bangla_doubled_consonant(text: str) -> tuple[str, int]:
    """
    Undo the consonant doubled before a pre-base vowel sign.

    **Mechanism.** `ো` (U+09CB) is canonically ` ে` + `া` — a vowel whose first
    component is drawn *before* the consonant it follows. Legacy Bangla
    encodings such as Bijoy store text in that visual order, so a converter that
    reads the pre-base component as a standalone character emits the consonant
    twice: `কো` becomes `ককো`.

    **Measured on the real corpus**, not assumed: 2,253 occurrences across
    **120 of 120 ICT records**. English and Physics are untouched, so this is an
    ICT extraction fault rather than a corpus-wide one.

        ককোননো      → কোনো        (364 occurrences)
        যযোগাযযোগ  → যোগাযোগ     (124)
        হললো        → হলো          (43)
        মততো        → মতো          (28)

    **Why this is safe.** Bengali orthography writes a true geminate as a
    conjunct with a virama — `ক্ক`, not `কক`. Two *bare* identical consonants
    before a vowel sign is not a spelling the script produces, so the pattern
    has no legitimate counterpart to destroy.

    The documented figure for this damage was "73 of 120 records". That came
    from an auditor pattern matching only `যয`, and undercounted the real
    damage by a factor of about nine.
    """
    return _DOUBLED_BEFORE_VOWEL.subn(r"\1\2", text)


def repair_bullet_glyph(text: str, min_bullets: int = 2) -> tuple[str, int]:
    """
    Restore list structure where a bullet was extracted as a lowercase `e`.

    **Measured:** 114 occurrences, all in English records. They sit *mid-line*,
    because the extractor lost the newlines too:

        "we will be able to e narrate incidents"
        "a logical sequence e participate in conversations"

    The corpus auditor reported zero of these. Its pattern anchored to a line
    start and required a following capital (`(?:^|\\n)\\s*e\\s+[A-Z]`), and
    neither survives once the line breaks are gone.

    **A single lone `e` is genuinely ambiguous** and is therefore left alone.
    "the letter e is a vowel" is ordinary prose in an English textbook, and no
    rule reading that sentence in isolation can distinguish it from a bullet.
    What distinguishes them is repetition: a bullet list has several bullets,
    and a sentence about the fifth letter of the alphabet has one. So this stage
    fires only where the text contains at least `min_bullets` of them.

    The replacement restores a newline as well as the bullet, which gives the
    re-chunker a real boundary to split on instead of an undifferentiated wall
    of text.
    """
    if len(_LONE_E.findall(text)) < min_bullets:
        return text, 0
    return _LONE_E.subn("\n• ", text)


def learn_true_compounds(texts: Iterable[str]) -> frozenset[str]:
    """
    Collect prefixes that legitimately keep a hyphen, from the corpus itself.

    `repair_hyphenated_line_break` has one genuinely ambiguous case. `prac- tise`
    must join to `practise`, but `multi- religious` must stay `multi-religious`,
    and no rule reading those two strings alone can tell them apart.

    The corpus can. A word hyphenated *without* a following space — `multi-racial`
    — is a real compound as extracted, so its prefix is one that keeps its
    hyphen. This was found in the corpus in the same sentence as the ambiguous
    case: "Sri Lanka is amulti- religious, multi-racial and multi-lingual".

    A prefix list would not have worked. `over` heads the true compound
    `over-the-counter` and also the line-broken `over- crowded`, so membership
    alone decides nothing; what decides it is whether *this corpus* uses the
    prefix hyphenated in running text.
    """
    seen: set[str] = set()
    for text in texts:
        for prefix, _ in _TRUE_COMPOUND.findall(text):
            seen.add(prefix.lower())
    return frozenset(seen)


def repair_hyphenated_line_break(
    text: str, true_compounds: frozenset[str] = frozenset()
) -> tuple[str, int]:
    """
    Rejoin a word split across a line break by the source PDF's hyphenation.

    **Measured:** 66 records — 50 ICT, 16 English.

        prac- tise      → practise
        domi- nated     → dominated
        comme- moration → commemoration
        begin- ning     → beginning

    A prefix in `true_compounds` keeps its hyphen and loses only the space, so
    `multi- religious` becomes `multi-religious` rather than `multireligious`.
    Pass the set from `learn_true_compounds` over the whole corpus; the default
    empty set means "join everything", which is the right behaviour for a single
    isolated string with no corpus to learn from.
    """
    count = 0

    def join(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        head, tail = match.group(1), match.group(2)
        if head.lower() in true_compounds:
            return f"{head}-{tail}"
        return f"{head}{tail}"

    return _SPLIT_WORD.sub(join, text), count


def normalise_whitespace(text: str) -> tuple[str, int]:
    """
    Collapse runs of spaces and trim line ends.

    Deliberately last. Every earlier stage measures positions in the text it was
    given, and collapsing whitespace first would move them. It counts a change
    per line it alters so the run report can distinguish "nothing was wrong" from
    "only spacing was wrong".
    """
    lines = text.split("\n")
    out, count = [], 0
    for line in lines:
        fixed = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        if fixed != line:
            count += 1
        out.append(fixed)
    joined = "\n".join(out)
    collapsed = re.sub(r"\n{3,}", "\n\n", joined)
    if collapsed != joined:
        count += 1
    return collapsed.strip(), count


# Order matters and is asserted by a test.
#
# Bangla repair runs before anything that measures length, because it removes
# 2,253 characters from the ICT corpus. The bullet stage runs before the
# re-chunker so the boundaries it inserts are available to split on. Whitespace
# runs last, once every other stage has finished moving text around.
STAGES: tuple[Stage, ...] = (
    Stage(
        name="bangla_doubled_consonant",
        description="consonant doubled before a pre-base vowel sign (ো/ে/ৌ)",
        apply=repair_bangla_doubled_consonant,
        languages=frozenset({"bn"}),
    ),
    Stage(
        name="bullet_glyph_e",
        description="bullet extracted as a lone lowercase 'e'",
        apply=repair_bullet_glyph,
        languages=frozenset({"en"}),
    ),
    Stage(
        name="hyphenated_line_break",
        description="word split across a line break by source hyphenation",
        apply=repair_hyphenated_line_break,
    ),
    Stage(
        name="whitespace",
        description="collapsed space runs and trailing whitespace",
        apply=normalise_whitespace,
    ),
)

STAGE_NAMES: tuple[str, ...] = tuple(s.name for s in STAGES)


def clean(
    text: str,
    *,
    language: str = "unknown",
    true_compounds: frozenset[str] = frozenset(),
    stages: Sequence[Stage] = STAGES,
) -> CleaningResult:
    """
    Run the stages that apply to this language, in order, reporting each.

    Unicode NFC is applied first so a stage never has to reason about two
    encodings of the same grapheme. `CanonicalChunk` normalises again on
    construction; doing it here as well is cheap and makes the stages
    independently correct rather than correct-only-in-context.

    A language of `unknown` runs only the language-agnostic stages. That is
    deliberate: guessing wrong and running Bangla repair over English would be a
    silent corruption, and no stage is worth that.
    """
    original = text
    current = unicodedata.normalize("NFC", text)
    changes: dict[str, int] = {}

    for stage in stages:
        if not stage.applies_to(language):
            continue
        if stage.name == "hyphenated_line_break":
            current, n = stage.apply(current, true_compounds)
        else:
            current, n = stage.apply(current)
        if n:
            changes[stage.name] = n

    return CleaningResult(text=current, original=original, changes=changes)
