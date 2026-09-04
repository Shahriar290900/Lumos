# Lumos Coverage Matrix

Derived from the curriculum registry. Verified 2026-09-04.
Machine-readable equivalent: `GET /curriculum`. Generated narrative: `CURRICULUM_INVENTORY.md`.

**Nothing is available.** No corpus has been ingested, so the API refuses every offering below before retrieval runs. That is the correct state, not a defect.

## Registered offerings

| Offering | Curriculum | Level | Sources | Audited records | Indexed | Status | MVP scope |
|---|---|---|---:|---:|---:|---|---|
| Physics | Edexcel IAL | International AS | 10 | — | 0 | in preparation | **Yes — the demo** |
| Physics | Edexcel IAL | International A2 | 10 | 17 | 0 | planned | Held, not indexed |
| ICT | NCTB | SSC | 6 | 120 | 0 | in preparation | Yes — target for publication |
| English | NCTB | SSC | 16 | 43 | 0 | in preparation | Yes — target for publication |
| Physics | NCTB | SSC | 0 | 0 | 0 | planned | Future |
| Chemistry | NCTB | SSC | 0 | 0 | 0 | planned | Future |
| Biology | NCTB | SSC | 0 | 0 | 0 | planned | Future |
| Mathematics | NCTB | SSC | 0 | 0 | 0 | planned | Future |
| Bangla | NCTB | SSC | 0 | 0 | 0 | planned | Future |

"Audited records" counts legacy source records that an auditor found; "Indexed" counts chunks actually in the store. They are different things and are stored in different tables (ADR-014).

## Demo scope — Edexcel IAL AS Physics

Units 1–3 for the 2024 May/June session, plus *Student Book 1*, whose Topics 1–4 cover the same AS content. That overlap is what makes the demo meaningful: a student's question can be answered from a textbook explanation, checked against a mark scheme, and enriched by an examiner's commentary on the same topic — which is the source hierarchy working, not just existing.

| Source layer | Documents | Priority | Route |
|---|---:|---:|---|
| Question papers (WPH11/12/13) | 3 | 1 | text |
| Mark schemes (WPH11/12/13) | 3 | 1 | text |
| Examiner reports (WPH11/12/13) | 3 | 1 | 2 need OCR, 1 text |
| *Student Book 1* | 1 | 2 | OCR (225 pages, no text layer) |

Measured: 41 main questions, 210 marks. Design in `docs/INGESTION_DESIGN.md`.

A2 units 4–6 are held and catalogued but out of scope — Student Book 1 covers AS content only, so A2 answers would rest on papers alone with no textbook layer beneath them.

## Readiness gates

| Gate | Edexcel AS | Edexcel A2 | NCTB ICT | NCTB English |
|---|---|---|---|---|
| Sources catalogued and checksummed | ✅ 10 | ✅ 10 | ✅ 6 | ✅ 16 |
| Ingestion route determined | ✅ | ✅ | ✅ structured | ✅ structured |
| Canonical schema | ❌ | ❌ | ❌ | ❌ |
| Deduplicated | n/a | ❌ dup in both repos | ❌ dup in both repos | ✅ |
| Extraction quality acceptable | ⚠️ OCR needed | ⚠️ OCR needed | ❌ 73 damaged records | ⚠️ bullet/truncation artefacts |
| Chunk size appropriate | not yet chunked | not yet chunked | ⚠️ ~1,800 chars | ❌ ~7,900 chars |
| Syllabus references | ⚠️ in textbook, OCR-fragile | ✅ `spec_ref` on legacy | ❌ none | ❌ none |
| Licence recorded | ✅ `permitted_private` | ✅ `permitted_private` | ❌ `unknown` | ❌ `unknown` |
| Indexed | ❌ | ❌ | ❌ | ❌ |
| Evaluation passed | ❌ | ❌ | ❌ | ❌ |

## Placeholder policy

Chemistry, Biology, Mathematics, Bangla and NCTB Physics are **registered as known-but-unavailable**, with `publication_status = 'planned'` and a bilingual `display_note`. They appear in the subject list so the roadmap is legible, and the schema refuses to store one without an explanation for the student.

The Bangla row is the regression guard. `Shikhbo-Local-App` v1.0.0 shipped a বাংলা subject button with no corpus behind it; selecting it returned nothing from the retriever and the model answered from its own priors, which looks like tutoring and is not. Two tests exist solely to keep that from returning — `test_subject_with_zero_chunks_is_never_available` and `test_tutor_refuses_an_unavailable_subject_before_retrieval`.

## The rule

An offering is `available` only when all of these hold, checked in one SQL view (ADR-013):

- `publication_status = 'published'`
- `indexing_status = 'indexed'`
- `evaluation_status = 'passed'`
- `indexed_chunk_count > 0`
- `licence_status` is `permitted_private` or `permitted_public`
- a syllabus version is set
- at least one language is set
- at least one source document exists

A UI tile, a route, a subject button, or a row in this table never means a subject is available.
