# AI Personal Assistant — résumé bullets

Human voice, every claim traceable to code in this repo.

## Full set

- Built an AI personal-assistant agent (Python, FastAPI, LangGraph, Next.js)
  that runs Gmail and Google Calendar actions behind a policy layer, with a
  human-in-the-loop approval gate — LangGraph `interrupt()` / `Command` resume —
  for every state-changing or high-risk action.
- Added retrieval over the user's email history: a Gmail ingestion pipeline
  (MIME parsing, ~1000-char chunking, `text-embedding-3-small`, idempotent
  upserts) behind a `VectorStore` interface with SQLite (NumPy cosine) and
  Postgres (pgvector + HNSW) implementations; recall questions are answered from
  the index with citations back to each source message.
- Hardened the agent against prompt injection with defense-in-depth: the
  boundary is a human approval gate on every send / delete / draft (an injected
  instruction can't act even undetected); on top, untrusted email text is fenced
  as data and run through a heuristic + optional-LLM screen that surfaces hits
  and bumps the policy decision. Wrote a three-corpus adversarial eval
  (literal / paraphrased / obfuscated) that reports per-corpus recall honestly
  rather than claiming injection is solved.
- Made it multi-user and deployable: "Sign in with Google" (the OAuth grant is
  the login) plus a guest mode, per-user tokens encrypted at rest, durable state
  in Postgres (LangGraph `PostgresSaver`, SQLAlchemy Core + Alembic) with a
  `DATABASE_URL`-selected SQLite path that keeps the 120-test suite
  network-free. Shipped as two Docker images with `docker compose`, Fly.io
  config, and a host-agnostic deploy guide.
- Replaced a 190-line keyword intent router with a hybrid classifier (keyword
  fast-path + LLM "second opinion" only when unsure), and added token streaming
  over SSE.

## Short set (3)

- Built a LangGraph agent (FastAPI + Next.js) for Gmail/Calendar with a
  risk-based policy layer and human approval on every sensitive action.
- Added email-history RAG (ingestion, embeddings, a SQLite/pgvector store, cited
  answers) and defended it against prompt injection — a human approval gate as
  the boundary, plus a fenced-content heuristic screen with an honest
  three-corpus adversarial eval.
- Took it multi-user and production-ready: Google sign-in + guest mode, per-user
  encrypted tokens, durable Postgres state, and a two-container Docker deploy
  with a 120-test no-network CI.
