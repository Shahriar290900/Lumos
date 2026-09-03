# Lumos Connector Registry

| Connector | Purpose | MVP | Config | Verification | Status |
|---|---|---:|---|---|---|
| GitHub | source control, CI | Yes | repo access; `GITHUB_TOKEN` only for automation | `gh auth status` | **Repo exists** |
| Neon | PostgreSQL 16 + pgvector + FTS | Yes | `DATABASE_URL`, `DIRECT_DATABASE_URL` | migration smoke test | **Not provisioned** (BLOCK-002) |
| Cloudflare | DNS, CDN, Workers | Yes | `CLOUDFLARE_ACCOUNT_ID`, scoped `CLOUDFLARE_API_TOKEN` | `wrangler whoami` | **Not provisioned** (BLOCK-003) |
| R2 | object storage | Yes | `R2_BUCKET_NAME`, `R2_ENDPOINT`, key pair or Worker binding | upload/read smoke test | **Not provisioned** (BLOCK-003) |
| Render | API service, ingestion worker, GPU | Yes | service credentials | `/health` returns 200 | **Not provisioned** (BLOCK-004) |
| Hugging Face | remote inference, model artifacts | Recommended for dev | `HF_TOKEN`, endpoint URL | inference smoke test | Account exists (`shahriarhameem`); no endpoint (BLOCK-005) |
| Model Gateway | internal abstraction over HF / Render / mock / Ollama | Yes | `AI_PROVIDER`, `AI_API_URL`, `AI_API_KEY` | gateway health check | **Not built** |
| Sentry | error monitoring | Recommended | `SENTRY_DSN` | deliberate test event | Not configured |
| Email | account, reset, contact | Recommended | provider key | sandbox send | **Not decided.** Legacy used Gmail SMTP app passwords — not production-grade |
| Payments | subscriptions | No | provider-specific | — | Later |

## Policy

- Secrets are never requested in chat, never committed, and never given a default value. A missing required secret aborts startup (ADR-012).
- Populate secrets in the provider dashboard and in a local `.env` that is gitignored. `.env.example` documents every variable's purpose, whether it is required, where it is used, and its development and production behaviour.
- API tokens are scoped to least privilege. A global Cloudflare key is not acceptable where a scoped token will do.
- No credential ever reaches the browser. A build-time check asserts that no `AI_*` or provider key appears in a client bundle.

## Development inference mode

The development machine is a 2017 MacBook Air and is a client, not an inference host.

1. **Mock provider first.** Deterministic, credential-free, and the reason CI and offline development work at all. Build this before any real provider.
2. **Then a cheap remote endpoint.** A T4-class HF Inference Endpoint or GPU Space with a 4B-class model — `Qwen/Qwen3.5-4B` or `google/gemma-4-E4B-it`, both Apache-2.0 and both verified to exist on the Hub.
3. **Measure** latency, context length, memory and Bangla answer quality against a real evaluation set before committing.
4. **Pause the endpoint between sessions**, and record the shutdown procedure and the budget ceiling (BLOCK-005). An endpoint left running over a weekend is the most likely way this project overspends.
5. **Move to Render GPU** only when uptime or traffic justifies it.

Embeddings and reranking use `BAAI/bge-m3` (MIT) and `BAAI/bge-reranker-v2-m3` (Apache-2.0). These are not candidates for substitution — the entire multilingual retrieval design depends on them.
