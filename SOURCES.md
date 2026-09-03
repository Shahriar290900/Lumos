# Source notes

## Project sources
- Shikhbo cloud reference: `https://github.com/Shahriar290900/shikhbo-ai` @ `64b58c9`
- Shikhbo local reference: `https://github.com/Shahriar290900/Shikhbo-Local-App` @ `b783680`
- Lumos repository: `https://github.com/Shahriar290900/Lumos`
- `Lumos_Whitepaper.pdf` — 10 pages, BCOLBD 2026 preliminary-round submission, dated 18 August 2026
- `BLOCKCHAIN OLYMPIAD BANGLADESH AI Guideline.pdf` — 6 pages, competition guideline and evaluation scheme
- `Lumos_Prebuild_Pack` and `Lumos_Prebuild_Pack 2` — design packs; `Pack 2` (post-RRF) is canonical, its data claims superseded by ADR-008
- Homepage start/end imagery and transition video — visual reference for LUMOS-017

## Verified in this session
- Corpus inventory: `scripts/audit_corpus.py` against both repository clones — `evidence/*.json`
- Model availability: live Hugging Face Hub lookups for all nine named models
- Secret scan: pattern search across all tracked files in both repositories — placeholders only
- Test inventory: filesystem scan for all common test conventions — none found

## Competition requirements (from the guideline PDF)

Preliminary round — white paper, max 10 pages, English, Times New Roman 12 pt. Scored /100: Vision & Problem Statement 30, Use Case & Existing Solutions 10, Risks and Challenges 20, Architecture & Infrastructure 30, Revenue & Distribution 10.

Final round — scored /100 across three components:

| Component | Points | Detail |
|---|---:|---|
| Technical documentation + code repository + inference model | 40 | Technical completeness & documentation 20; **code quality & inference model, including reproducibility** 20 |
| Demo video (max 10 min, English or English-subtitled) | 30 | Functionality demonstration 15; presentation quality 15 |
| Live presentation (English, 1-min per-member intro) | 30 | Impact & innovation 15; delivery 15 |

The reproducibility criterion is why BLOCK-001 is rated critical: an evaluator can compare the whitepaper's corpus claims against the repository in minutes.

## Technology references
- TanStack Start: `https://tanstack.com/start/latest`
- Cloudflare R2: `https://developers.cloudflare.com/r2/`
- Render background workers: `https://render.com/docs/background-workers`
- pgvector: `https://github.com/pgvector/pgvector`

## Note on figures
Pricing and provider limits quoted in the whitepaper (§5.11) and in the prebuild pack's `HUGGINGFACE_DEV_MODE.md` are from mid-2026 list prices and were **not re-verified in this session**. Re-check at provisioning time (BLOCK-005).
