# AI Personal Assistant

A production-style AI personal assistant: a **LangGraph** agent behind a
**FastAPI** API and a **Next.js** chat UI, wired to Gmail and Google Calendar,
with a **policy layer** that classifies every action by risk and a
**human-in-the-loop approval** gate before anything user-facing happens.

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
- **Prompt-injection guardrails**: every piece of untrusted email text is
  fenced as data and screened; a detected injection attempt is surfaced and
  ignored, never acted on. Adversarial eval in `eval/redteam.py`
- **Policy + approval**: read-only actions run freely; state-changing and
  high-risk actions are gated by an explicit approve/reject step
- User memory & preferences (SQLite), timezone-aware scheduling
- Daily briefing (emails + calendar + tasks), task / follow-up tracking,
  meeting-prep assistant
- LangSmith tracing on every node

## Architecture

```mermaid
flowchart TD
    UI["Next.js chat UI<br/>+ approval cards"] -->|POST /chat| API["FastAPI"]
    API --> G["LangGraph assistant graph"]

    subgraph G["LangGraph assistant graph (InMemorySaver checkpointer)"]
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

    G <-->|memory / tasks| DB[("SQLite")]
    RET <-->|vector search| VDB[("email_chunks<br/>SQLite + NumPy cosine")]
    TOOL <-->|Gmail / Calendar API| GOOG["Google APIs"]
    G -.->|traces| LS["LangSmith"]
```

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

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in OPENAI_API_KEY etc. (see below)
# put your Google OAuth client file at backend/client_secret.json
uvicorn app:app --reload    # http://localhost:8000
```

Then connect Google: open `http://localhost:8000/auth/google/start`.

**Environment** (`backend/.env`):

| var | notes |
| --- | --- |
| `OPENAI_API_KEY` | required (unless `LLM_PROVIDER=ollama`) |
| `OPENAI_MODEL` | default `gpt-4.1-mini` |
| `EMBEDDING_MODEL` | default `text-embedding-3-small` |
| `LLM_PROVIDER` | `openai` \| `openai_first` (OpenAI, then local Ollama) \| `ollama` |
| `HISTORY_INGEST_MAX_MESSAGES` | default `200` |
| `INJECTION_LLM_CHECK` | escalate borderline injection checks to the LLM (default off) |
| `SESSION_SECRET` | signs the OAuth cookie — **must** be set in production |
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
python -m pytest                    # 110 tests — no network, no API keys
python -m eval.run_eval             # LLM eval harness (needs a live model)
python -m eval.redteam              # prompt-injection screen: precision/recall
```

The pytest suite covers the policy layer, intent routing, memory CRUD, the
timezone/time-parsing helpers, the retrieval store + ingestion, the
injection/redaction guards, and the whole graph end-to-end (including the
approve/reject resume, RAG with citations, and a poisoned email being flagged
rather than obeyed) with a fake LLM, fake embeddings, and fake Google clients.
`eval/redteam.py` scores the injection screen against a labelled adversarial
corpus and gates on zero missed attacks.

## Project structure

```txt
backend/
  app.py                  FastAPI: /chat, /chat/stream, /chat/approve,
                          /history/index, Google OAuth
  config.py               env-driven settings
  graph/
    assistant_graph.py    the LangGraph StateGraph (39 nodes)
    nodes.py              LLM extraction, policy, responders (incl. respond_history)
    intent.py             hybrid keyword + LLM intent classifier
    tools.py              Gmail / Calendar / retrieve_history tool nodes
    policy.py             action → risk → decision (+ untrusted_injection signal)
    memory.py             SQLite preferences + tasks
    state.py              AssistantState TypedDict
  retrieval/
    embeddings.py         OpenAI / Ollama embeddings
    store.py              VectorStore interface + SqliteVectorStore
    ingest.py             Gmail → chunk → embed → upsert  (+ CLI)
    search.py             embed query → cosine top-k
  security/
    injection.py          prompt-injection heuristics (+ optional LLM)
    redaction.py          PII redaction for logs / traces
    guard.py              fence untrusted text + report
  integrations/           gmail_client, calendar_client, google_auth
  models/schemas.py       pydantic request / extraction models
  eval/                   scenario dataset + evaluators + runner + redteam
  tests/                  pytest suite

frontend/
  app/                    Next.js app router
  components/             ChatBox, MessageList, ApprovalCard
  lib/                    api client + shared types
```

## Design decisions & tradeoffs

- **SQLite + NumPy cosine, not a vector DB.** One mailbox indexes to a few
  thousand chunks; a full scan is sub-10 ms and adds no service to run or
  deploy. `VectorStore` is an interface — `PgVectorStore` (pgvector + HNSW)
  drops in when the app goes multi-tenant.
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
