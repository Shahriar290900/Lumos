# Lumos Checklist

## Reconnaissance — complete (2026-09-04)
- [x] Clone and audit both legacy repositories
- [x] Read all RAG, ingestion, retrieval and model-integration code
- [x] Parse and audit every JSONL corpus file
- [x] Verify the corpus baseline independently (three methods)
- [x] Read both prebuild packs, the whitepaper and the competition guideline
- [x] Verify every named model exists on the Hugging Face Hub
- [x] Scan both repositories for committed secrets
- [x] Inventory tests and CI
- [x] Produce `RECONNAISSANCE_REPORT.md` and the governing documents
- [x] Record blockers
- [x] Commit to the Lumos repository

## Human setup — outstanding
- [ ] Decide the whitepaper corpus position (BLOCK-001) — **critical**
- [ ] Create the Neon project, enable pgvector, choose the region (BLOCK-002)
- [ ] Create the Cloudflare zone and R2 bucket; decide the domain (BLOCK-003)
- [ ] Create Render services (BLOCK-004)
- [ ] Choose the model provider, model, and **budget ceiling + shutdown procedure** (BLOCK-005)
- [ ] Choose the auth provider (BLOCK-006)
- [ ] Decide the under-18 data policy (BLOCK-007)
- [ ] Establish source licensing status (BLOCK-008)
- [ ] Locate the source PDFs behind the ICT corpus, if they exist (BLOCK-009)

## Repository — next
- [ ] Monorepo layout (`apps/`, `services/`, `packages/`, `tests/`)
- [ ] `.claude/agents` and `.claude/skills`
- [ ] Hooks that block completion on failing tests
- [ ] Lint, typecheck, format for both TypeScript and Python
- [ ] `.env.example` committed; `.env` gitignored and never committed
- [ ] CI that runs the full suite with an empty `.env` via the mock provider

## Verification gates — none passed yet
- [ ] `pnpm` toolchain works
- [ ] Python environment works
- [ ] Local Postgres with pgvector works
- [ ] Neon connectivity verified
- [ ] Cloudflare auth verified
- [ ] R2 upload/read verified
- [ ] Render health check verified
- [ ] Model Gateway health check verified against a real provider
- [ ] Model Gateway health check verified against the mock provider
- [ ] Playwright installed; baseline test passes

## Human approvals required
- [ ] Product scope
- [ ] Source corpus and licensing
- [ ] Under-18 data policy
- [ ] Model selection
- [ ] Cost ceiling
- [ ] Deployment regions and data retention

## Competition readiness (BCOLBD final round)
- [ ] Technical documentation an external evaluator can follow (`/docs`)
- [ ] Code repository complete, documented, reproducible from a clean clone
- [ ] Deployment-ready inference model demonstrated
- [ ] Demo video, max 10 minutes, English or English-subtitled
- [ ] Live presentation with a 1-minute intro per team member
- [ ] **Whitepaper claims reconciled with repository reality** (BLOCK-001)
