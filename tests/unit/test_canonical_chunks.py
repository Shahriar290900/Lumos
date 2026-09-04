"""
The canonical chunk model, without a database.

Identity, determinism, provenance honesty and the question-boundary rule are all
pure functions of their input, so they are tested as such. No fixture here
contains real examination material: the papers are licensed, and a test suite is
a published artifact. The synthetic paper below reproduces the *structure* the
reconnaissance verified — the terminator, the sub-part labels, the mark
allocations, the margin boilerplate — with invented physics.
"""

from __future__ import annotations

import uuid

import pytest

from services.ingestion.canonical import (
    CHUNK_KEY_VERSION,
    INGESTION_VERSION,
    LUMOS_CHUNK_NAMESPACE,
    CanonicalChunk,
    count_tokens,
    make_chunk_id,
    make_chunk_key,
    normalise_text,
    sha256_text,
)
from services.ingestion.legacy_adapter import (
    LegacyDocument,
    detect_language,
    reconcile_chapter,
    record_to_chunk,
)
from services.ingestion.past_paper import (
    clean_paper_text,
    detect_sub_parts,
    parse_questions,
    questions_to_chunks,
)

SHA_A = "a" * 64
SHA_B = "b" * 64

DOC_ID = "11111111-1111-1111-1111-111111111111"
OFFERING_ID = "22222222-2222-2222-2222-222222222222"


def make_chunk(**overrides) -> CanonicalChunk:
    base = dict(
        source_document_id=DOC_ID,
        offering_id=OFFERING_ID,
        document_sha256=SHA_A,
        locator="q/1",
        text="A trolley of mass 2.0 kg accelerates uniformly from rest.",
        chunk_type="exam_question",
        question_number="1",
        extraction_method="pdf_text_layer",
    )
    base.update(overrides)
    return CanonicalChunk(**base)


# ─────────────────────────────────────────────────────────────────────────────
# Identity
# ─────────────────────────────────────────────────────────────────────────────

def test_chunk_key_embeds_document_and_locator():
    key = make_chunk_key(SHA_A, "q/12")
    assert key == f"lumos:v{CHUNK_KEY_VERSION}:{SHA_A}:q/12"


def test_chunk_id_is_deterministic():
    key = make_chunk_key(SHA_A, "q/12")
    assert make_chunk_id(key) == make_chunk_id(key)
    assert make_chunk_id(key) == uuid.uuid5(LUMOS_CHUNK_NAMESPACE, key)


def test_same_input_produces_the_same_chunk_twice():
    a, b = make_chunk(), make_chunk()
    assert a.id == b.id
    assert a.chunk_key == b.chunk_key
    assert a.content_sha256 == b.content_sha256
    assert a.fingerprint() == b.fingerprint()


def test_same_question_number_in_different_documents_does_not_collide():
    """
    The identity guarantee that matters.

    "Question 12" exists in every paper ever printed. Because the document's
    checksum is inside the key, question 12 of one paper and question 12 of
    another are different chunks — no session or paper-code convention required.
    """
    first = make_chunk(document_sha256=SHA_A, locator="q/12", question_number="12")
    second = make_chunk(document_sha256=SHA_B, locator="q/12", question_number="12")
    assert first.id != second.id
    assert first.chunk_key != second.chunk_key


def test_same_document_different_question_does_not_collide():
    a = make_chunk(locator="q/12", question_number="12")
    b = make_chunk(locator="q/13", question_number="13")
    assert a.id != b.id


def test_identical_text_in_two_documents_shares_content_hash_but_not_identity():
    """
    Cross-document duplicate detection without identity collision.

    137 legacy records exist byte-identically in two repositories. They must be
    *detectable* as duplicates and still be separately addressable, because they
    belong to different registered documents.
    """
    a = make_chunk(document_sha256=SHA_A, text="Identical wording.")
    b = make_chunk(document_sha256=SHA_B, text="Identical wording.")
    assert a.content_sha256 == b.content_sha256
    assert a.id != b.id


def test_chunk_key_rejects_a_missing_or_malformed_document_checksum():
    for bad in ("", "not-a-hash", "A" * 63, "z" * 64):
        with pytest.raises(ValueError):
            make_chunk_key(bad, "q/1")


def test_chunk_key_rejects_an_empty_locator():
    with pytest.raises(ValueError):
        make_chunk_key(SHA_A, "   ")


def test_fingerprint_changes_when_any_persisted_field_changes():
    base = make_chunk()
    for field, value in [
        ("text", "Different wording entirely."),
        ("marks", 5),
        ("page_number", 7),
        ("language", "bn"),
        ("extraction_method", "ocr_tesseract"),
        ("topic", "Momentum"),
        ("notes", "changed"),
    ]:
        changed = make_chunk(**{field: value})
        assert changed.fingerprint() != base.fingerprint(), f"{field} did not affect the fingerprint"


def test_fingerprint_is_stable_across_equal_but_distinct_objects():
    a = make_chunk(keywords=["force", "mass"], sub_parts=[{"label": "(a)", "marks": 3}])
    b = make_chunk(keywords=["force", "mass"], sub_parts=[{"label": "(a)", "marks": 3}])
    assert a.fingerprint() == b.fingerprint()


# ─────────────────────────────────────────────────────────────────────────────
# Provenance
# ─────────────────────────────────────────────────────────────────────────────

def test_extraction_method_and_ingestion_version_are_always_recorded():
    chunk = make_chunk()
    assert chunk.extraction_method == "pdf_text_layer"
    assert chunk.ingestion_version == INGESTION_VERSION


def test_untouched_text_is_labelled_verbatim_and_keeps_no_duplicate():
    chunk = make_chunk(text="Clean text with nothing to normalise.")
    assert chunk.provenance_status == "verbatim"
    assert chunk.text_raw is None


def test_transformed_text_is_labelled_and_keeps_the_original():
    """A transformation you cannot inspect is a transformation you cannot trust."""
    raw = "Trailing spaces   \nand a combining sequence: é"
    chunk = make_chunk(text=raw)
    assert chunk.provenance_status == "normalized"
    assert chunk.text_raw == raw
    assert chunk.text != raw


def test_ocr_output_can_be_declared_uncertain():
    chunk = make_chunk(extraction_method="ocr_tesseract",
                       provenance_status="ocr_uncertain",
                       extraction_confidence=0.71)
    assert chunk.provenance_status == "ocr_uncertain"
    assert chunk.extraction_confidence == 0.71


def test_an_explicit_provenance_status_is_not_overridden():
    """
    An OCR adapter knows its output is uncertain even when NFC changed nothing.
    The adapter's judgement wins over the inference.
    """
    chunk = make_chunk(text="Already clean.", extraction_method="ocr_tesseract",
                       provenance_status="ocr_uncertain")
    assert chunk.provenance_status == "ocr_uncertain"


def test_unknown_values_are_explicit_not_guessed():
    chunk = CanonicalChunk(
        source_document_id=DOC_ID, offering_id=OFFERING_ID,
        document_sha256=SHA_A, locator="legacy/X-1",
        text="Some content.", chunk_type="legacy_record", legacy_chunk_id="X-1")
    assert chunk.extraction_method == "unknown"
    assert chunk.language == "unknown"
    assert chunk.page_number is None
    assert chunk.syllabus_reference is None
    assert chunk.topic is None
    assert chunk.marks is None


def test_empty_text_is_a_parsing_failure_not_a_valid_chunk():
    with pytest.raises(ValueError, match="no text"):
        make_chunk(text="   \n  ")


def test_unknown_enumerated_values_are_rejected():
    with pytest.raises(ValueError):
        make_chunk(chunk_type="something_else")
    with pytest.raises(ValueError):
        make_chunk(extraction_method="magic")
    with pytest.raises(ValueError):
        make_chunk(provenance_status="probably_fine")


def test_content_hash_is_of_the_stored_text():
    chunk = make_chunk(text="Exactly this.")
    assert chunk.content_sha256 == sha256_text(chunk.text)


def test_token_count_is_recomputed_per_script():
    english = make_chunk(text="one two three four five", language="en")
    assert english.token_count == 5
    bangla_text = "তথ্য ও যোগাযোগ প্রযুক্তি একুশ শতক"
    bangla = make_chunk(text=bangla_text, language="bn")
    # Bangla subword tokenisation runs well ahead of whitespace-word count, so a
    # word count would misreport it; the estimate must not simply be len(split()).
    assert bangla.token_count > len(bangla_text.split())


def test_normalise_text_reports_whether_it_changed_anything():
    assert normalise_text("clean") == ("clean", "verbatim")
    text, status = normalise_text("trailing   \n\n\nspaces  ")
    assert status == "normalized"
    assert not text.endswith(" ")


def test_count_tokens_is_deterministic():
    assert count_tokens("some text here", "en") == count_tokens("some text here", "en")


# ─────────────────────────────────────────────────────────────────────────────
# Legacy adapter
# ─────────────────────────────────────────────────────────────────────────────

LEGACY_DOC = LegacyDocument(
    path=__import__("pathlib").Path("ICT_C1.jsonl"),
    source_document_id=DOC_ID, offering_id=OFFERING_ID,
    declared_language="bn", sha256=SHA_A)

LEGACY_RECORD = {
    "chunk_id": "SSC-ICT-C1-P1-CH1",
    "class": "SSC",
    "subject": "ICT",
    "chapter_no": "1",
    "chapter_title": "অধ্যায় এক",
    "page_no": 1,
    "topic": "তথ্য ও যোগাযোগ",
    "prerequisite": "Basic Computer Knowledge",
    "keywords": [],
    "token_count": 2099,
    "content": "তথ্য ও যোগাযোগ প্রযুক্তি একুশ শতকের সম্পদ।",
}


def test_legacy_record_converts_and_stays_traceable():
    chunk = record_to_chunk(LEGACY_RECORD, LEGACY_DOC, ordinal=0)
    assert chunk.chunk_type == "legacy_record"
    assert chunk.extraction_method == "structured_jsonl"
    assert chunk.legacy_chunk_id == "SSC-ICT-C1-P1-CH1"
    assert chunk.locator == "legacy/SSC-ICT-C1-P1-CH1"
    # The original record is kept whole, so normalisation stays reversible.
    assert chunk.legacy_metadata["record"] == LEGACY_RECORD
    assert chunk.legacy_metadata["source_file"] == "ICT_C1.jsonl"


def test_legacy_token_count_is_preserved_but_not_used():
    chunk = record_to_chunk(LEGACY_RECORD, LEGACY_DOC, ordinal=0)
    assert chunk.legacy_token_count == 2099
    assert chunk.token_count != 2099   # recomputed from the actual text


def test_chapter_title_and_chapter_name_both_resolve():
    """
    The 80/100 split that made both legacy apps display 'Chapter N: None'.
    Reading only one field is the defect; reading either is the fix.
    """
    assert reconcile_chapter({"chapter_title": "One"}) == ("One", "chapter_title")
    assert reconcile_chapter({"chapter_name": "Two"}) == ("Two", "chapter_name")
    assert reconcile_chapter({}) == (None, None)
    assert reconcile_chapter({"chapter_name": "   "}) == (None, None)


def test_the_field_a_chapter_label_came_from_is_recorded():
    chunk = record_to_chunk({**LEGACY_RECORD, "chapter_title": None,
                             "chapter_name": "Unit three"}, LEGACY_DOC, 0)
    assert chunk.section_ref == "Unit three"
    assert chunk.legacy_metadata["chapter_field_used"] == "chapter_name"


def test_language_is_derived_from_the_script_not_the_filename():
    assert detect_language("তথ্য ও যোগাযোগ", None) == "bn"
    assert detect_language("Force and motion", None) == "en"
    # A declared language is a fallback, never an override of the evidence.
    assert detect_language("তথ্য", "en") == "bn"
    assert detect_language("", None) == "unknown"


def test_missing_legacy_fields_become_explicit_nulls():
    sparse = {"chunk_id": "X-1", "content": "Some text."}
    chunk = record_to_chunk(sparse, LEGACY_DOC, 0)
    assert chunk.section_ref is None
    assert chunk.topic is None
    assert chunk.syllabus_reference is None
    assert chunk.page_number is None
    assert chunk.prerequisite_text is None
    assert chunk.keywords == []
    assert chunk.legacy_token_count is None


def test_legacy_record_without_an_identifier_is_refused():
    with pytest.raises(ValueError, match="no chunk_id"):
        record_to_chunk({"content": "orphan"}, LEGACY_DOC, 0)


def test_legacy_record_without_content_is_refused():
    with pytest.raises(ValueError, match="no content"):
        record_to_chunk({"chunk_id": "X-1", "content": "  "}, LEGACY_DOC, 0)


def test_spec_ref_survives_when_the_source_has_one():
    chunk = record_to_chunk({**LEGACY_RECORD, "spec_ref": "5.6.154, 5.6.155"},
                            LEGACY_DOC, 0)
    assert chunk.syllabus_reference == "5.6.154, 5.6.155"


# ─────────────────────────────────────────────────────────────────────────────
# Question boundaries
# ─────────────────────────────────────────────────────────────────────────────
#
# Synthetic. Structure verified against real papers; physics invented.

SYNTHETIC_PAGE_1 = """\
*Z12345A0104*
DO
NOT
WRITE
IN
THIS
AREA
AERA SIHT NI ETIRW TON OD
SECTION A
1 A cart rolls down a slope. Which quantity is a vector?
A speed
B distance
C velocity
D energy
(Total for Question 1 = 1 mark)
2 Which unit measures power?
A joule
B watt
C newton
D pascal
(Total for Question 2 = 1 mark)
2
"""

SYNTHETIC_PAGE_2 = """\
3
*Z12345A0304*
 Turn over
DO NOT WRITE IN THIS AREA
3 A block of mass 4.0 kg rests on a horizontal surface.
(a) Calculate the weight of the block.
.................................................................................
                                                              (2)
(b) The block is pushed with a force of 20 N.
(i) Determine the resultant force.
.................................................................................
                                                              (3)
(ii) Explain why the block accelerates.
.................................................................................
                                                              (2)
(Total for Question 3 = 7 marks)
"""

SYNTHETIC_PAPER = [(1, SYNTHETIC_PAGE_1), (2, SYNTHETIC_PAGE_2)]


def test_the_terminator_finds_every_question_and_its_marks():
    questions, report = parse_questions(SYNTHETIC_PAPER)
    assert [q.question_number for q in questions] == ["1", "2", "3"]
    assert [q.marks for q in questions] == [1, 1, 7]
    assert report.questions_found == 3
    assert report.total_marks == 9
    assert report.numbering_gaps == []


def test_a_complete_question_stays_one_unit_with_all_its_sub_parts():
    """
    The multi-part mechanism, in one assertion.

    Question 3 has (a), (b)(i) and (b)(ii). All three must be inside a single
    chunk, because that is what makes the context for (b)(ii) available whenever
    (b)(ii) is retrieved — no dependency graph required (ADR-016).
    """
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    q3 = next(q for q in questions if q.question_number == "3")

    assert "Calculate the weight" in q3.text
    assert "Determine the resultant force" in q3.text
    assert "Explain why the block accelerates" in q3.text

    labels = [p["label"] for p in q3.sub_parts]
    assert labels == ["(a)", "(b)", "(b)(i)", "(b)(ii)"]
    assert [p["marks"] for p in q3.sub_parts] == [2, None, 3, 2]

    chunks = questions_to_chunks(
        [q3], source_document_id=DOC_ID, offering_id=OFFERING_ID,
        document_sha256=SHA_A, extraction_method="pdf_text_layer")
    assert len(chunks) == 1, "a question must not be split into per-part chunks"
    chunk = chunks[0]
    assert chunk.question_number == "3"
    # The chunk is the whole question, so claiming a sub-part identifier would
    # misrepresent what was stored.
    assert chunk.sub_question is None
    assert chunk.marks == 7
    assert len(chunk.sub_parts) == 4
    assert chunk.depends_on == []


def test_multiple_choice_questions_have_no_sub_parts():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    assert questions[0].sub_parts == []
    assert questions[1].sub_parts == []


def test_question_chunks_record_the_pages_they_span():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    q3 = next(q for q in questions if q.question_number == "3")
    assert q3.page_start is not None and q3.page_end is not None
    assert q3.page_end >= q3.page_start


def test_layout_furniture_is_removed_and_the_raw_text_is_kept():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    q3 = next(q for q in questions if q.question_number == "3")
    for noise in ("DO NOT WRITE IN THIS AREA", "AERA SIHT NI ETIRW TON OD",
                  "Turn over", "*Z12345A0304*", "........."):
        assert noise not in q3.text, f"{noise!r} survived cleaning"
    # Nothing is silently discarded: the untouched extraction is retained.
    assert "DO NOT WRITE IN THIS AREA" in q3.text_raw


def test_cleaning_never_alters_wording():
    text = clean_paper_text("A block of mass 4.0 kg rests on a surface.\n"
                            "DO NOT WRITE IN THIS AREA\n.................")
    assert text == "A block of mass 4.0 kg rests on a surface."


def test_question_chunks_are_marked_cleaned_and_keep_their_raw_text():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    chunks = questions_to_chunks(
        questions, source_document_id=DOC_ID, offering_id=OFFERING_ID,
        document_sha256=SHA_A, extraction_method="pdf_text_layer")
    assert all(c.provenance_status == "cleaned" for c in chunks)
    assert all(c.text_raw for c in chunks)


def test_ocr_sourced_questions_are_marked_uncertain():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    chunks = questions_to_chunks(
        questions, source_document_id=DOC_ID, offering_id=OFFERING_ID,
        document_sha256=SHA_A, extraction_method="ocr_tesseract")
    assert all(c.provenance_status == "ocr_uncertain" for c in chunks)
    assert all(c.extraction_method == "ocr_tesseract" for c in chunks)


def test_a_gap_in_question_numbering_is_reported_not_ignored():
    """
    Numbers run 1..N continuously in these papers. A gap means the parser lost a
    question, which must reach the ingestion report rather than disappear.
    """
    pages = [(1, "1 First question.\n(Total for Question 1 = 1 mark)\n"
                 "3 Third question.\n(Total for Question 3 = 2 marks)\n")]
    _, report = parse_questions(pages)
    assert report.numbering_gaps == ["2"]
    assert any("not contiguous" in w for w in report.warnings)


def test_a_paper_with_no_terminator_yields_nothing_rather_than_guessing():
    _, report = parse_questions([(1, "Some prose with no question boundaries.")])
    assert report.questions_found == 0


def test_sub_part_marks_attach_to_the_part_above_them():
    parts = detect_sub_parts("(a) First part.\n(3)\n(b) Second part.\n(5)")
    assert parts == [
        {"label": "(a)", "level": 1, "marks": 3},
        {"label": "(b)", "level": 1, "marks": 5},
    ]


def test_a_bare_number_outside_a_sub_part_is_not_read_as_marks():
    parts = detect_sub_parts("(7)\n(a) A part.\n(2)")
    assert parts == [{"label": "(a)", "level": 1, "marks": 2}]


def test_questions_to_chunks_orders_them_and_records_the_method():
    questions, _ = parse_questions(SYNTHETIC_PAPER)
    chunks = questions_to_chunks(
        questions, source_document_id=DOC_ID, offering_id=OFFERING_ID,
        document_sha256=SHA_A, extraction_method="pdf_text_layer")
    assert [c.ordinal for c in chunks] == [0, 1, 2]
    assert all(c.chunk_type == "exam_question" for c in chunks)
    assert all(c.extraction_method == "pdf_text_layer" for c in chunks)
