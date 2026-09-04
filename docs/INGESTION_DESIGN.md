# Lumos Ingestion Design — Edexcel IAL AS Physics

Written after inspecting the actual source documents on 2026-09-04. Every claim
below was verified by extracting from the files, not inferred from their names.

**Scope:** Edexcel IAL AS Physics — Units 1–3 (WPH11, WPH12, WPH13), 2024 May/June
session, plus *Student Book 1*. Registered as `edexcel-ial/physics/international-as`.
A2 units 4–6 are held and catalogued but out of scope; Student Book 1 covers
Topics 1–4, which is AS content, so those units would have papers with no
textbook layer beneath them.

**Status:** design only. No ingestion has run. This document is the input to
LUMOS-007.

---

## 1. What the sources actually are

| Document | Count | Pages | Text layer | Route |
|---|---:|---:|---|---|
| Question papers WPH11–13 | 3 | 76 | clean | parse |
| Mark schemes WPH11–13 | 3 | 45 | clean, tabular | parse |
| Examiner reports WPH11–13 | 3 | 166 | **varies per document** | mixed |
| *Student Book 1* | 1 | 225 | **none at all** | OCR |

Measured content: **41 main questions across the three papers, 210 marks**
(WPH11: 19 questions / 80 marks; WPH12: 18 / 80; WPH13: 4 / 50).

The routing decision is per document, not per corpus. Within a single session's
examiner reports: WPH11 and WPH13 decode to `(cid:N)` glyph references, WPH12
and WPH15 extract cleanly, WPH14 and WPH16 are mixed. `scripts/catalog_sources.py`
records the verdict per file and the registry stores it in
`source_documents.ingestion_route`, so the pipeline never has to guess.

---

## 2. Question papers — parse

### Boundary detection

The whitepaper's design is confirmed. `(Total for Question N = M marks)` is a
**100 % reliable terminator**: 19 of 19 in WPH11, and it carries the mark total,
so boundary and marks come from one match.

```
(Total for Question 1 = 1 mark)      ← Section A, multiple choice
(Total for Question 19 = 12 marks)   ← Section B, structured
```

Use the terminator as the primary anchor and the opening pattern (`^N ` at the
start of a question) as validation, not the other way round. Question numbers
restart at 1 and run continuously, so a gap in the sequence is a parse failure
and should fail the ingestion report rather than silently drop a question.

### Sub-question structure

`(a)`, `(b)`, `(c)` with nested `(i)`, `(ii)`. Per-part marks appear as a bare
parenthesised integer on its own line:

```
(a) Calculate the weight of the block of ice.
    density of seawater = 1.03 × 10³ kg m⁻³
                                                              (3)
```

Parse sub-parts within an already-bounded question, never across the whole
document — the bare `(3)` is far too ambiguous to anchor on globally.

### Dependency edges — a finding that changes the plan

**No explicit dependency cross-reference exists in any of the three AS papers.**
A scan for "your answer to", "answer to part", "value calculated in", "use your",
"obtained in" and related phrasings returns zero matches across all three,
excluding the boilerplate asterisk instruction.

The whitepaper describes extracting a `depends_on` array from phrases like
"using your answer from part (a)". That mechanism has nothing to operate on here.

This is not a problem, because the chunking policy already solves it: **one
complete main question, all parts included, is one chunk.** Sub-parts of a
question are never separated, so the context needed to explain part (c) is
present whenever part (c) is retrieved — by construction rather than by parsed
edges. The per-question scratchpad then accumulates across sub-parts within that
retrieved unit.

`depends_on` stays in the schema as an enhancement for sessions that do contain
explicit references. It is not a prerequisite for multi-part tutoring, and
LUMOS-016 should not be blocked on it.

### Cleaning — required before embedding

Verified noise in the extracted text, all of which would otherwise pollute
embeddings and the lexical index:

| Artefact | Example |
|---|---|
| Margin boilerplate | `DO NOT WRITE IN THIS AREA` |
| The same, mirrored | `AERA SIHT NI ETIRW TON OD` |
| Print codes | `*P75806A0228*` |
| Page furniture | `Turn over`, bare page numbers |
| Answer-line dot leaders | `..................` runs of 150+ characters |
| Maths glyph failures | `(cid:30)q (cid:31) p(cid:29)(cid:28)R` |

The dot leaders are the worst offender by volume — a structured question page can
be majority leader characters. Strip them before any length or token calculation,
or every chunk-size measurement will be wrong.

For the glyph failures: the **mark scheme is the repair source**. Mark schemes
carry proper Unicode mathematics for the same questions —
`𝑠 = 𝑢𝑡 + ½𝑎𝑡²`, `𝑡 = 1.13 s` — so a formula lost in the question paper is
recoverable from the linked mark-scheme chunk rather than reconstructed.

### Figures

Diagrams carry third-party attributions: `(Source: © Doug Allan / Science Photo
Library)`. Generating searchable alt-text from a figure and storing that text is
retrieval context. Extracting, storing or serving the figure image itself is
redistribution of third-party material. **Alt-text yes, image storage no**, until
BLOCK-008 is resolved. The attribution line must be retained in the chunk so the
provenance is never lost.

---

## 3. Mark schemes — parse, with two strategies

Clean text throughout, laid out as `Question Number | Answer | Mark` tables.
Structured questions terminate with `Total for question N  <marks>`; that
terminator appears 9 / 8 / 4 times across WPH11/12/13 — but the papers hold
19 / 18 / 4 questions.

The difference is Section A. Multiple-choice answers live in a table with no
terminator at all:

```
8  The correct answer is A (The ball bearing is moving downwards when   1
   the student starts the stopwatch)
   B is incorrect because time would be greater giving a lower value
```

So the mark-scheme parser needs **two strategies**: terminator-bounded blocks for
structured questions, and row extraction (`pdfplumber.extract_tables`) for the
MCQ section. The distractor explanations — "B is incorrect because…" — are
genuinely valuable teaching content and should be captured, not discarded as
table noise.

Link each mark-scheme chunk to its question chunk by `(paper_code, question_number)`.
That linkage is what lets source priority put the official answer above a
textbook passage on the same topic.

---

## 4. Examiner reports — route per document, then OCR where needed

Where a text layer exists, parse it. Where it does not, the failure mode is
specific: the PDF embeds subset fonts with no `ToUnicode` CMap, so *every*
extractor — pdfplumber, pypdf, pdfium, poppler — returns `(cid:N)` references
rather than characters. This is not recoverable by trying another library.

**OCR works well.** Rendering at 300 DPI and running Tesseract on WPH11's
examiner report produces clean prose:

> Question 11 (a)-(b)
>
> Q11(a) was generally well answered, with most candidates correctly applying the
> equation for gravitational potential energy. A small proportion of candidates
> truncated their calculated answer from 417 × 10⁵ J to 410 × 10⁵ J instead of
> correctly rounding it to 420 × 10⁵ J.

The `Question N (a)-(b)` headers survive OCR and give reliable chunk boundaries
keyed straight to question numbers.

**Discard candidate script images.** Examiner reports interleave photographed
handwritten answers with "ResultsPlus / Examiner Comments" analysis. The
handwriting OCRs to noise:

> is is eo spite / Swe. 93% 1:08. +. XP 14 ¥f08 "= EO Bo

Drop text preceding an `Examiner Comments` marker within a ResultsPlus block, and
apply a confidence floor. The examiner's commentary that follows is exactly the
pedagogical content the tutor wants — it explains *why* a mark was or was not
awarded — and it is the single strongest argument for keeping examiner reports in
the corpus despite the OCR cost.

---

## 5. Textbook — full OCR

*Student Book 1* has **no text layer on any of its 225 pages**. 102 MB of page
scans. Every page must be rendered and OCR'd.

Quality at 250 DPI is good:

> **1A 1 VELOCITY AND ACCELERATION**
> LEARNING OBJECTIVES
> ■ Explain the distinction between scalar and vector quantities.
> ■ Distinguish between speed and velocity and define acceleration.

Structural markers that survive OCR and give chunk boundaries: `CHAPTER`,
`SPECIFICATION REFERENCE`, `LEARNING OBJECTIVES`, and section headings of the
form `<topic><letter> <n> <TITLE>`.

Two known weaknesses:

1. **Specification references OCR badly.** `1.3.1 1.3.4` comes back as `131 134`
   — decimal points lost in a small-font sidebar. These references are the link
   between textbook sections and exam questions, so they matter more than most
   text. Re-OCR the specification-reference region at higher DPI with a
   digit-and-period character allowlist, and validate against the known
   specification numbering before accepting.
2. **Equations degrade.** `speed (ms⁻¹) = distance (m) / time (s)` becomes
   `speed (ms!) = edi idl`. Fractions and superscripts are the common failures.
   Flag low-confidence equation regions rather than indexing them silently, and
   prefer the mark-scheme formulae where the same relationship appears.

Chunk at section headings, 400–600 tokens with 50-token overlap, per the
whitepaper's textbook policy.

**Compute note.** 225 pages of render-plus-OCR is a batch job, not a request-path
operation. It runs once, off the development machine, and its output is cached by
`provenance_hash` so a re-run does not repeat it.

---

## 6. Pipeline

```
catalogue (scripts/catalog_sources.py)      checksum, page count, route
    │
    ├── route = text ────► extract → clean → structure → chunk
    ├── route = ocr ─────► render 250-300 DPI → OCR → confidence filter
    │                       → discard handwriting regions → clean → chunk
    └── route = mixed ───► per page: text if present, else OCR
    │
    ▼
link            question ↔ mark scheme ↔ examiner report, by (paper_code, question_number)
    │           textbook section ↔ specification reference
    ▼
normalise       canonical chunk schema (docs/CHUNK_SCHEMA.md)
    ▼
quality score   OCR confidence, boilerplate ratio, equation-region flags, boundary integrity
    ▼
embed           BGE-M3 via the Model Gateway
    ▼
lexical index   Postgres FTS
    ▼
report          per-document ingestion report → human review
    ▼
registry        indexed_chunk_count, indexing_status='indexed'
                (publication still requires evaluation_status='passed')
```

Every stage is a pure function over its input with the original text retained
alongside the cleaned text, so any transformation can be inspected, re-run or
reversed.

---

## 7. Safety rules

These are constraints on the pipeline, not aspirations.

1. **Source documents never enter version control.** Enforced by `.gitignore`,
   by `.githooks/pre-commit` (which blocks `private_source_materials/`, any PDF
   outside `docs/`, and any file over 10 MB), and by a CI job that fails if
   either is tracked. `git add -f` does not get past the hook.
2. **Derived text is licensed too.** Extracted chunks are Pearson content in
   another form. They are retrieval context, never redistributed: the tutor
   returns generated explanations with citations, never reproduced source text,
   and no page image is served to a student.
3. **Provenance on every chunk.** `provenance_hash` resolves to an exact file by
   SHA-256 and an exact page. A citation that cannot be traced back to a page in
   a catalogued document is a bug.
4. **Extracted text is untrusted input.** A curriculum PDF is an external
   document. Retrieved text is delimited structurally in the prompt, instruction-
   like patterns are stripped at ingest, and no chunk may alter system
   instructions. This holds even though the sources are reputable — the control
   is on the channel, not on the publisher.
5. **No corpus is published on an unknown licence.** The schema enforces it
   (`offering_published_needs_licence`). The Edexcel material is currently
   `permitted_private`; public availability needs BLOCK-008 resolved.
6. **Ingestion is off the development machine.** The 2017 MacBook Air is a
   client. OCR and embedding run as batch jobs elsewhere.
7. **Nothing is published unreviewed.** Each document produces an ingestion
   report — pages processed, OCR confidence distribution, questions found versus
   expected, chunks emitted, artefacts flagged — and a human reads it before
   `indexing_status` moves to `indexed`.

---

## 8. What this predicts

From 41 main questions, 3 mark schemes, 3 examiner reports and 225 textbook
pages, a first ingestion should produce roughly:

- ~41 question chunks (one per main question, all parts together)
- ~41 mark-scheme chunks, linked one-to-one
- ~60–120 examiner-report chunks (one per question-commentary block)
- ~400–600 textbook chunks at 400–600 tokens

That is a few hundred chunks over one examination session and one textbook —
small enough to evaluate honestly, and structured enough to demonstrate source
priority, citation resolution and multi-part continuity on real material.

The figure is a prediction, not a result. It goes in the ingestion report and is
compared against reality; a large divergence means the parser is wrong, not that
the estimate was.
