# AI Personal Assistant

A production-style AI personal assistant built with FastAPI, LangGraph, Next.js, Gmail API, Google Calendar API, Google Meet, memory, task tracking, and human-in-the-loop approval.

## Features

- Chat-based AI assistant
- Gmail unread email summaries
- Gmail draft creation
- Gmail reply draft creation
- Google Calendar event creation
- Google Meet link generation
- Calendar conflict detection
- Human approval before sensitive actions
- User memory and preferences
- Timezone-aware scheduling
- Daily briefing with emails, calendar, tasks, and follow-ups
- Task and follow-up reminder tracking
- Meeting prep assistant with talking points and suggested actions
- LangSmith tracing

## Tech Stack

### Backend
- FastAPI
- Python
- LangGraph
- LangSmith
- OpenAI
- Gmail API
- Google Calendar API
- SQLite memory store

### Frontend
- Next.js
- React
- Tailwind CSS
- Approval cards
- Chat UI

## Project Structure

```txt
backend/
  app.py
  config.py
  graph/
    assistant_graph.py
    nodes.py
    tools.py
    state.py
    memory.py
    policy.py
  integrations/
    gmail_client.py
    calendar_client.py
    google_auth.py
  models/
    schemas.py
  storage/
    tokens.json

frontend/
  app/
  components/
  package.json