# AI Personal Assistant

A production-style AI personal assistant: a **LangGraph** agent behind a
**FastAPI** API and a **Next.js** chat UI, wired to Gmail and Google Calendar,
with a **policy layer** that classifies every action by risk and a
**human-in-the-loop approval** gate before anything user-facing happens.
Multi-user (Google sign-in + guest mode), durable state in Postgres, and
deployable as two containers — see [`docs/deploy.md`](docs/deploy.md).

**Live:** https://ai-assistant-frontend-akshar.fly.dev (backend:
https://ai-assistant-backend-akshar.fly.dev) — Fly.io + Postgres/pgvector.
Free-tier machines scale to zero, so the first request after idle takes a
few seconds to cold-start.

## Features

- Chat assistant with token streaming (SSE) and an LLM fallback (OpenAI → Ollama)
- **Hybrid intent classifier**: deterministic keyword routing with an LLM
  "second opinion" only when the keywords are unsure
- Gmail: unread-email summaries, draft creation, reply drafts, **send** (gated)
- Google Calendar: event creation, conflict detection, Google Meet links,
  **event deletion** (gated)
- **RAG over your email history**: `Index email history` embeds recent Gmail;
  recall questions ("when does our contract renew?") are answered from the
  index with inline citations back to each message
- **Prompt-injection defense-in-depth**: the boundary is the approval gate —
  send / delete / draft always require a human, so an injection in an email
  body can't cause an action even if nothing detects it. On top of that, every
  piece of untrusted email text is fenced as data and run through a heuristic
  screen; a hit is surfaced to the user and bumps the policy decision. The
  screen is a filter, not the wall — `eval/redteam.py` measures it honestly
  (near-100% on literal attacks, ~75% on paraphrases, the rest contained)
- **Policy + approval**: read-only actions run freely; state-changing and
  high-risk actions are gated by an explicit approve/reject step
- **Multi-user**: "Sign in with Google" (the OAuth grant *is* the login) or a
  guest session (chat + memory + tasks, no Google data). Per-user Google tokens
  encrypted at rest; signed session cookie
- **Durable state**: conversation checkpoints, preferences, tasks, tokens, and
  email-history vectors all in Postgres (SQLite for local/tests) via
  `DATABASE_URL`; Alembic migrations
- Daily briefing (emails + calendar + tasks), task / follow-up tracking,
  meeting-prep assistant
- LangSmith tracing on every node

## Architecture

```mermaid
flowchart TD
    UI["Next.js chat UI<br/>+ approval cards"] -->|POST /chat| API["FastAPI"]
    API --> G["LangGraph assistant graph"]

    UI -->|Sign in with Google / guest| AUTH["/auth · session cookie<br/>per-user encrypted tokens"]

    subgraph G["LangGraph assistant graph"]
        DI["detect_intent"] --> PREP["prepare_* node<br/>(LLM structured extraction)"]
        PREP --> POL["policy_check<br/>risk → allow / require_approval / deny / clarify"]
        POL -->|allow| TOOL["Gmail / Calendar tool"]
        POL -->|require_approval| INT["interrupt() → wait for human"]
        INT -->|Command(resume=approved)| TOOL
        TOOL --> DONE["reply"]
    end

    DI -->|recall question| RET["retrieve_history<br/>embed query → cosine top-k"]
    RET --> GUARD["guard: fence + injection scan"]
    GUARD --> ANS["grounded answer + citations"]

    G <-->|"checkpoints · memory · tasks · tokens"| DB[("Postgres<br/>(SQLite locally)")]
    RET <-->|vector search| VDB[("email_chunks<br/>pgvector / SQLite+NumPy")]
    AUTH <--> DB
    TOOL <-->|Gmail / Calendar API| GOOG["Google APIs"]
    G -.->|traces| LS["LangSmith"]
```

State persistence is `DATABASE_URL`-driven: `InMemorySaver` + SQLite locally
(the test suite needs no database), `PostgresSaver` + pgvector in production.

### Retrieval + guardrails

`Index email history` (button, `POST /history/index`, or
`python -m retrieval.ingest`) pulls recent Gmail, extracts plain-text bodies,
chunks them (~1000 chars / 150 overlap), embeds with `text-embedding-3-small`,
and upserts into a SQLite vector store — idempotent per message. A recall
question routes to `retrieve_history` (embed the query, NumPy cosine top-k) and
then to `respond_history`, which **fences every retrieved chunk** in
`<untrusted_content>` tags and runs it through `security/injection.py` before it
reaches the model. A flagged chunk gets a visible "ignored injected
instructions" notice instead of being obeyed, and the `evaluate_policy`
`untrusted_injection` signal bumps an otherwise-auto-allowed action to
`require_approval`. See `docs/rag-and-guardrails.md`.

The **approval flow** uses LangGraph's `interrupt()`: when `policy_check` returns
`require_approval`, the graph pauses and the API returns an `approval_payload`.
The UI shows an approval card; on approve, the frontend calls `/chat/approve`
which resumes the same graph thread with `Command(resume={"approved": true})`.

## Run it

### Everything at once (Docker)

```bash
cp backend/.env.docker.example backend/.env    # fill in the secrets
docker compose up --build                      # frontend :3000 · backend :8000 · postgres :5432
```
Runs Postgres + pgvector, applies migrations, and serves both apps.

### Backend only (local dev, SQLite)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in OPENAI_API_KEY, SESSION_SECRET, TOKEN_ENCRYPTION_KEY
# put your Google OAuth client file at backend/client_secret.json
alembic upgrade head        # creates storage/app.db
uvicorn app:app --reload    # http://localhost:8000
```

Open the frontend, then **Sign in with Google** or **Continue as guest**.

**Environment** (`backend/.env`):

| var | notes |
| --- | --- |
| `OPENAI_API_KEY` | required (unless `LLM_PROVIDER=ollama`) |
| `OPENAI_MODEL` | default `gpt-4.1-mini` |
| `EMBEDDING_MODEL` | default `text-embedding-3-small` |
| `LLM_PROVIDER` | `openai` \| `openai_first` (OpenAI, then local Ollama) \| `ollama` |
| `HISTORY_INGEST_MAX_MESSAGES` | default `200` |
| `INJECTION_LLM_CHECK` | escalate borderline injection checks to the LLM (default off) |
| `DATABASE_URL` | default `sqlite:///storage/app.db`; a `postgresql://…` URL in prod |
| `SESSION_SECRET` | signs the session cookie — **must** be set in production |
| `TOKEN_ENCRYPTION_KEY` | Fernet key encrypting per-user Google tokens; required once anyone signs in |
| `GOOGLE_REDIRECT_URI` | default `http://localhost:8000/auth/google/callback` |
| `FRONTEND_ORIGIN` | default `http://localhost:3000` |
| `LANGSMITH_API_KEY` / `LANGSMITH_TRACING` | optional tracing |

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env
npm run dev                 # http://localhost:3000
```

## Tests & eval

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest                    # 122 tests — no network, no API keys, SQLite
python -m eval.run_eval             # LLM eval harness (needs a live model)
python -m eval.redteam              # prompt-injection screen: precision/recall
```

The pytest suite covers the policy layer, intent routing, memory CRUD, the
timezone/time-parsing helpers, the retrieval store + ingestion, the
injection/redaction guards, and the whole graph end-to-end (including the
approve/reject resume, RAG with citations, and a poisoned email being flagged
rather than obeyed) with a fake LLM, fake embeddings, and fake Google clients.
`eval/redteam.py` scores the injection screen against three corpora (literal /
paraphrased / obfuscated attacks + a benign false-positive set) and reports
per-corpus recall. CI gates only on literal recall and the false-positive rate
— reworded attacks that slip the filter are *contained* by the approval gate,
which `test_containment_holds_even_when_the_heuristic_misses` asserts directly.

## Project structure

```txt
backend/
  app.py                  FastAPI: /auth/*, /chat, /chat/stream, /chat/approve,
                          /history/index
  config.py               env-driven settings
  db/
    engine.py             SQLAlchemy engine from DATABASE_URL (lazy, resettable)
    tables.py             Core tables: users, preferences, tasks, google_tokens
  alembic/                migrations
  auth/
    session.py            signed session cookie (itsdangerous)
    tokens.py             per-user Google creds, Fernet-encrypted at rest
    users.py              Google `sub` / guest user rows
    context.py            request-scoped user id (ContextVar) for integrations
    deps.py               FastAPI current_user dependency
  graph/
    assistant_graph.py    LangGraph StateGraph (39 nodes); Postgres/InMemory checkpointer
    nodes.py              LLM extraction, policy, responders (incl. respond_history)
    intent.py             hybrid keyword + LLM intent classifier
    tools.py              Gmail / Calendar / retrieve_history tool nodes
    policy.py             action → risk → decision (+ untrusted_injection signal)
    memory.py             preferences + tasks (on the DB engine)
  retrieval/
    embeddings.py         OpenAI / Ollama embeddings
    store.py              VectorStore: SqliteVectorStore | PgVectorStore (pgvector)
    ingest.py             Gmail → chunk → embed → upsert  (+ CLI)
    search.py             embed query → cosine top-k
  security/
    injection.py          prompt-injection heuristics (+ optional LLM)
    redaction.py          PII redaction for logs / traces
    guard.py              fence untrusted text + report
  integrations/           gmail_client, calendar_client, google_auth
  eval/                   scenario dataset + evaluators + runner + redteam
  tests/                  pytest suite (SQLite, no network)
  Dockerfile

frontend/
  app/ components/ lib/   Next.js UI, api client, shared types
  Dockerfile              multi-stage Next standalone

docker-compose.yml · backend/fly.toml · frontend/fly.toml · render.yaml
```

## Design decisions & tradeoffs

- **One `DATABASE_URL`, two dialects.** SQLite locally and in CI means the test
  suite stays network- and service-free (122 tests, ~2s); Postgres + pgvector
  in production. `db/` is SQLAlchemy Core + Alembic; `VectorStore` has a
  `SqliteVectorStore` (NumPy cosine — sub-10 ms over one mailbox) and a
  `PgVectorStore` (pgvector + HNSW), picked by URL.
- **Google sign-in *is* the login.** The OAuth grant the app already needs for
  Gmail/Calendar doubles as authentication (`sub` = user id), so there's no
  separate password system. Guest mode gives a no-Google session so the live
  demo works without handing over an inbox.
- **No host-specific code.** The app is configured entirely through env vars and
  ships as plain Dockerfiles; `fly.toml` / `render.yaml` are thin wrappers, and
  `docs/deploy.md` has a "switching hosts" checklist.
- **Heuristics before LLM, everywhere.** Intent classification and injection
  screening both run deterministic rules first and only call a model when the
  rules are unsure. Cheaper, faster, and testable without a network; the LLM is
  a fallback, not the default path.
- **Injection screening surfaces, it doesn't silently drop.** A flagged email
  still gets summarized — the user sees a notice that injected instructions were
  ignored. Combined with the existing approval gate (draft/send/delete already
  need a human), the realistic threat — the agent *acting* on injected text — is
  closed without making the assistant useless on legitimately weird email.
- **Redaction is for logs, not model input.** Redacting PII before the model
  sees it would break "what's the address in that email?". Redaction lives at
  the logging / tracing boundary instead.
- **`interrupt()` for approval, not a separate approvals table.** The graph
  pauses mid-execution and resumes the same thread with `Command(resume=…)`, so
  approved actions run with the exact state they were planned against.

## Out of scope (intentionally)

Multi-user auth (tokens are a single local file), a real job queue for
ingestion (it's synchronous and bounded), HTML email rendering fidelity,
and calendar recurrence editing.
