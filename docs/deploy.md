# Deploying

The app is a plain two-container stack (FastAPI + Next.js) plus Postgres. There
is **no host-specific code** — everything is configured through env vars, so the
same images run on Fly, Render, Railway, a VPS with `docker compose`, or
anything else that runs a container. Fly is the reference host below.

## What you need first

1. **Google OAuth client** (Google Cloud Console → APIs & Services → Credentials
   → OAuth client ID → Web application). You'll add the real redirect URI once
   you know the backend URL. Download the client-secret JSON.
2. **OpenAI API key**.
3. Two generated secrets:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"          # SESSION_SECRET
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEY
   ```

## Local (docker compose)

```bash
cp backend/.env.docker.example backend/.env   # fill in the secrets above
docker compose up --build
# frontend  http://localhost:3000
# backend   http://localhost:8000
```
Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI
on the OAuth client. The backend container runs `alembic upgrade head` on start.

## Fly.io

```bash
# --- backend ---
cd backend
fly launch --no-deploy --copy-config --name ai-assistant-backend
fly postgres create --name ai-assistant-db --region sjc
fly postgres attach ai-assistant-db          # sets DATABASE_URL

fly secrets set \
  OPENAI_API_KEY=sk-... \
  SESSION_SECRET=... \
  TOKEN_ENCRYPTION_KEY=... \
  GOOGLE_CLIENT_SECRET_JSON="$(cat /path/to/client_secret.json)" \
  FRONTEND_ORIGIN=https://ai-assistant-frontend.fly.dev \
  GOOGLE_REDIRECT_URI=https://ai-assistant-backend.fly.dev/auth/google/callback

fly deploy

# --- frontend ---
cd ../frontend
# set build.args.NEXT_PUBLIC_API_BASE_URL in fly.toml to the backend URL first
fly launch --no-deploy --copy-config --name ai-assistant-frontend
fly deploy
```

Finally, in the Google Cloud console add
`https://ai-assistant-backend.fly.dev/auth/google/callback` as an authorized
redirect URI.

`pgvector` ships in Fly Postgres 16+; `PgVectorStore.init()` runs
`CREATE EXTENSION IF NOT EXISTS vector` on first use.

## Switching hosts

Nothing in `backend/` or `frontend/` references Fly. To move:

1. Stand up Postgres 16+ **with the `vector` extension available** on the new host.
2. Give the backend container these env vars: `DATABASE_URL`, `OPENAI_API_KEY`,
   `SESSION_SECRET`, `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_SECRET_JSON`,
   `FRONTEND_ORIGIN`, `GOOGLE_REDIRECT_URI`, `APP_ENV=production`.
3. Build the frontend image with `--build-arg NEXT_PUBLIC_API_BASE_URL=<backend url>`.
4. Run `alembic upgrade head` once (release/pre-deploy hook, or the compose
   `command`).
5. Update the OAuth redirect URI in Google Cloud.

`render.yaml` in the repo root is a Render blueprint doing exactly this — it's
the only file that differs between hosts.

## Notes

- Free-tier machines scale to zero; the first request after idle cold-starts in
  a few seconds. Set `min_machines_running = 1` to keep it warm.
- Conversation state (LangGraph checkpoints), preferences, tasks, encrypted
  Google tokens, and email-history vectors all live in the one Postgres
  database — back that up, not the containers.
