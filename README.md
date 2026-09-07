# AI Personal Assistant

A production-style AI personal assistant: a **LangGraph** agent behind a
**FastAPI** API and a **Next.js** chat UI, wired to Gmail and Google Calendar,
with a **policy layer** that classifies every action by risk and a
**human-in-the-loop approval** gate before anything user-facing happens.

## Features

- Chat assistant with an LLM fallback (OpenAI → Ollama)
- Gmail: unread-email summaries, draft creation, reply drafts
- Google Calendar: event creation, conflict detection, Google Meet links
- **Policy + approval**: read-only actions run freely; state-changing actions
  (drafts, calendar writes) are gated by an explicit approve/reject step
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

    G <-->|memory / tasks| DB[("SQLite")]
    TOOL <-->|Gmail / Calendar API| GOOG["Google APIs"]
    G -.->|traces| LS["LangSmith"]
```

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
| `LLM_PROVIDER` | `openai` \| `openai_first` (OpenAI, then local Ollama) \| `ollama` |
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
python -m pytest                    # 49 tests — no network, no API keys
python -m eval.run_eval             # LLM eval harness (needs a live model)
```

The pytest suite covers the policy layer, keyword intent routing, memory CRUD,
the timezone/time-parsing helpers, and the whole graph end-to-end (including the
approve/reject resume) with a fake LLM and fake Google clients. The eval harness
in `backend/eval/` runs 11 scenarios against a real model and scores intent /
policy / draft-completeness.

## Project structure

```txt
backend/
  app.py                  FastAPI: /chat, /chat/approve, Google OAuth
  config.py               env-driven settings
  graph/
    assistant_graph.py    the LangGraph StateGraph (32 nodes)
    nodes.py              intent detection, LLM extraction, policy, responders
    tools.py              Gmail / Calendar tool nodes
    policy.py             action → risk → decision
    memory.py             SQLite preferences + tasks
    state.py              AssistantState TypedDict
  integrations/           gmail_client, calendar_client, google_auth
  models/schemas.py       pydantic request / extraction models
  eval/                   scenario dataset + evaluators + runner
  tests/                  pytest suite

frontend/
  app/                    Next.js app router
  components/             ChatBox, MessageList, ApprovalCard
  lib/                    api client + shared types
```
