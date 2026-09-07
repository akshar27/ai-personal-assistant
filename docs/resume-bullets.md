# AI Personal Assistant — résumé bullets

Human voice, every claim traceable to code in this repo.

## Full set

- Built an AI personal-assistant agent (Python, FastAPI, LangGraph, Next.js)
  that runs Gmail and Google Calendar actions behind a policy layer, with a
  human-in-the-loop approval gate — using LangGraph `interrupt()` / `Command`
  resume — for every state-changing or high-risk action.
- Added retrieval over the user's email history: a Gmail ingestion pipeline
  (MIME parsing, ~1000-char chunking, `text-embedding-3-small`, idempotent
  upserts) and a SQLite + NumPy-cosine vector store behind a `VectorStore`
  interface; recall questions are answered from the index with citations back
  to each source message.
- Hardened the agent against prompt injection: all untrusted email text is
  fenced as data and screened by a deterministic heuristic layer (with an
  optional LLM escalation); detected attempts are surfaced and ignored rather
  than executed, and feed an `untrusted_injection` policy signal. Wrote an
  adversarial eval (`eval/redteam.py`) that gates on zero missed attacks.
- Replaced a 190-line keyword `detect_intent` with a hybrid classifier —
  keyword fast-path plus an LLM "second opinion" only when the heuristic is
  unsure, degrading silently to a safe default on any LLM failure.
- Added token streaming over SSE and a fake-LLM / fake-Google / fake-embeddings
  pytest suite (110 tests, no network) plus a CI workflow (pytest + lint +
  build).

## Short set (3)

- Built a LangGraph agent (FastAPI + Next.js) for Gmail/Calendar with a
  risk-based policy layer and human approval (`interrupt()`/resume) on every
  sensitive action.
- Added email-history RAG — ingestion, chunking, embeddings, a pluggable SQLite
  vector store, and cited answers — and hardened the agent against prompt
  injection with a fenced-content + heuristic screen and an adversarial eval.
- Shipped token streaming (SSE), a hybrid keyword+LLM intent classifier, and a
  110-test no-network suite with CI.
