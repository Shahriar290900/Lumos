# Lumos — Handoff

For running Lumos on a machine with a real GPU. Written 2026-09-04.

**Live now:** https://shahriarhameem-lumos.hf.space
**Source:** https://github.com/Shahriar290900/Lumos

The thing this machine unlocks is **generation**. Everything else already works:
the corpus is normalised, embedded and searchable, retrieval scores recall@1 of
1.000 on known-item evaluation, and citations are validated. What is missing is
a model to write the explanation, because `gemma4:e4b` is not served by any
Hugging Face inference provider and the development machine is a 2017 MacBook
Air with no GPU.

---

## 1. Get it running (about ten minutes)

```bash
git clone https://github.com/Shahriar290900/Lumos.git && cd Lumos
git config core.hooksPath .githooks        # licensed-material guard; do not skip

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env                        # then fill it in — see §2
```

The licensed PDFs are **not** in the repository and never will be (ADR-017).
They are in the private Cloudflare R2 bucket `lumos-curriculum`, and the
credentials are in the project owner's `.env`. Ask him; do not commit them.

## 2. What `.env` needs

| Variable | Where it comes from | Needed for |
|---|---|---|
| `DATABASE_URL` | Neon, **unpooled** host (no `-pooler`) | everything |
| `HF_TOKEN` | Hugging Face, scope `inference.serverless.write` | embeddings |
| `AI_PROVIDER` | `ollama` on this machine | generation |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | generation |
| `CHAT_MODEL` | `gemma4:e4b` — do not change (ADR-022) | generation |

`HF_TOKEN` is still required with `AI_PROVIDER=ollama`. Generation runs locally
and embeddings stay on Hugging Face, because the corpus is indexed with
`BAAI/bge-m3` and embedding queries with a different model would put query and
document vectors in different spaces.

## 3. Turn generation on

```bash
ollama pull gemma4:e4b
ollama serve                     # 127.0.0.1:11434

ollama show gemma4:e4b           # ← verify the tag; BLOCK-005 wants this recorded
```

Then:

```bash
export AI_PROVIDER=ollama
python -m uvicorn apps.api.main:app --port 8000
curl localhost:8000/health       # expect "generation": "live"
```

`/health` reports whether generation **works**, not which provider is set. If it
says `unavailable`, the note explains why.

## 4. Run the tests

Skipped during the last stretch of development at the owner's request, so **run
these first** — some of the newest code has been import-checked and run against
the real corpus, but not unit-tested.

```bash
export TEST_DATABASE_URL="$DATABASE_URL"   # unpooled
AI_PROVIDER=mock pytest                    # 220 tests, no credential needed
```

The suite runs entirely on the mock provider. If a test needs a GPU or an API
key, that test is wrong.

**Not yet covered by tests**, written after testing was paused:

- `services/models/providers/ollama.py` and `SplitProvider` in `gateway.py`
- `services/ingestion/mark_scheme.py` — run against all six real papers instead
- `services/ingestion/ocr.py` — never executed; tesseract is not installed here

## 5. Finish the ingestion

### Mark schemes — parser works, not yet loaded

Verified against the real PDFs. The three AS papers are exact:

| Paper | Found / expected | Distractor explanations |
|---|---|---|
| WPH11 | 19 / 19 | 30 |
| WPH12 | 18 / 18 | 28 |
| WPH13 | 4 / 4 | 0 |
| WPH14 | 9 / 18 | 3 |
| WPH15 | 10 / 20 | 0 |
| WPH16 | 4 / 4 | 0 |

WPH14 and WPH15 are A2, outside the demo scope, and are missing their
multiple-choice sections — almost certainly a **third** phrasing. WPH11 writes
"The correct answer is A" and WPH12 writes "B is the correct answer"; assuming
one house style across a single session has now been wrong twice, so read the
text before adding a pattern.

### Textbook OCR — code written, never run

`services/ingestion/ocr.py` renders with `pypdfium2` and OCRs with Tesseract,
one page at a time. 225 pages, roughly 30–60 minutes on a decent CPU.

```bash
brew install tesseract                     # or apt-get install tesseract-ocr
pip install pypdfium2 pytesseract
```

Watch for two known weaknesses, both handled but neither verified: specification
references OCR as `131` instead of `1.3.1`, and equations degrade badly. Pages
below 70% mean confidence are marked `ocr_uncertain` rather than stored as
exact.

***Student Book 1* is never served to a student** — grounding only (ADR-026). The
18 exam PDFs may be served. The `source_documents.delivery` column enforces this
and defaults to `none`.

## 6. Things that will surprise you

Each of these cost time to find. They are recorded so they do not cost it twice.

**The reranker made retrieval nineteen times worse.** Measured, on the same
corpus and queries:

| | recall@1 | recall@5 |
|---|---|---|
| Reranking off | 1.000 | 1.000 |
| Reranking on | 0.053 | 0.526 |

`BAAI/bge-reranker-v2-m3` is not reachable as a cross-encoder over Hugging Face
serverless. The pipeline that answers computes bi-encoder cosine, which returns
about 0.9 for everything — so it looked like it was working. It is off by
default; `RERANK_ENABLED=1` turns it back on, and **re-measure before trusting
it**.

**The mock provider is not a placeholder.** Its embeddings are 1024-dimensional
unit vectors, so a dimension mismatch cannot hide. Its answers say they are
mocked, in the text. Do not "improve" it into producing plausible prose.

**`plainto_tsquery` cannot be used here.** It ANDs every term, and the index uses
the `simple` configuration so Bangla is not mangled, which means nothing is a
stopword. It matched zero chunks for ordinary questions. Lexical search ORs its
terms deliberately.

**Migration `down --to 0001` reverts the registry too.** Versions compare as
strings and `"0001_curriculum_registry" > "0001"`. Use the full version name.

**Running the migration reversal test wipes the embeddings**, because dropping
the column drops the data. Re-run `scripts/embed_corpus.py` afterwards; it is
resumable and only embeds what is missing.

## 7. What is actually finished

14 of 33 goals. `CHECKLIST.md` is accurate and was rewritten against measured
reality, not intention.

**Works:** curriculum registry with coverage gates · canonical chunk model ·
Bangla repair across all 120 ICT records · English re-chunking · hybrid
retrieval over 373 real embeddings · citation validation · model gateway with
the single-model policy enforced in code · the interface · Space deployment.

**Not built:** authentication · student dashboard · practice engine · 3D
homepage · examiner-report ingestion · textbook ingestion · voice · the
evaluation harness beyond retrieval.

**Blocked on a human:** a generation endpoint and its budget ceiling
(BLOCK-005) · legal review of `docs/UNDER_18_POLICY.md` (BLOCK-007) · locating
the 2.58 GB corpus the whitepaper claims (BLOCK-001A) · whether the NCTB corpora
may be published at all (BLOCK-008).

## 8. Rules that are not negotiable

Read `CLAUDE.md` before changing anything. The short version:

1. **Never commit `private_source_materials/`.** Three guards exist. Do not
   weaken them, and do not use `git add -f` or `--no-verify`.
2. **`gemma4:e4b` is the only generation model** (ADR-022). No fallback. If it is
   unavailable, fail loudly.
3. **A subject is available only when the registry says so.** Never because a
   card or route exists.
4. **Never fabricate curriculum data** to make a subject look complete.
5. **A goal is done when its evidence is recorded**, not when it builds.
