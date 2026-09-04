---
title: Lumos
emoji: 🪄
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Curriculum-grounded AI tutor for Bangladeshi students
---

# Lumos — Lights the Way to Knowledge

A curriculum-grounded tutor. Every citation resolves to a real page in a real
document, and insufficient evidence produces a stated limitation rather than a
confident guess.

**Source:** https://github.com/Shahriar290900/Lumos

## What this Space runs

The FastAPI service and the interface, against a Neon Postgres database holding
the curriculum registry and the embedded corpus. Retrieval is hybrid — Postgres
full-text search and pgvector, fused with Reciprocal Rank Fusion.

## Required secrets

Set these in **Settings → Variables and secrets**:

| Secret | Purpose |
|---|---|
| `DATABASE_URL` | Neon connection string, unpooled |
| `HF_TOKEN` | embeddings via `BAAI/bge-m3` |
| `AI_PROVIDER` | `huggingface`, or `mock` to run without any credential |

## Honest state

Generation is **not wired up**. `gemma4:e4b` has no inference endpoint, so the
tutor returns retrieval and real citations and says plainly that it cannot write
the explanation. It does not substitute another model — that is a deliberate
policy (ADR-022), not a missing feature.

Reranking is **off**, because measurement showed the available cross-encoder
endpoint made retrieval nineteen times worse at rank 1.
