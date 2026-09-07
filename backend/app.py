import json
import logging

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from langgraph.types import Command

from models.schemas import ChatRequest, ChatResponse, ApprovalRequest, HistoryIndexRequest
from graph.assistant_graph import build_graph
from graph.memory import init_memory
from retrieval.ingest import ingest_user_history
from retrieval.store import get_store
from integrations.google_auth import create_flow, client_id
from auth import session
from auth.context import user_scope
from auth.deps import current_user, current_user_optional
from auth.users import User, create_guest_user, touch_user, upsert_google_user
from auth.tokens import save_user_tokens, delete_user_tokens
from config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ai_assistant.api")

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.is_production,
    same_site="lax",
)

init_memory()
graph = build_graph()


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        session.COOKIE_NAME,
        session.issue(user_id),
        max_age=session.MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------ auth

@app.get("/auth/google/start")
def auth_google_start(request: Request):
    try:
        flow = create_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        request.session["oauth_state"] = state
        request.session["code_verifier"] = flow.code_verifier
        return RedirectResponse(authorization_url)
    except Exception:
        logger.exception("google auth start failed")
        raise HTTPException(status_code=500, detail="Could not start Google authorization.")


@app.get("/auth/google/callback")
def auth_google_callback(request: Request, code: str, state: str):
    try:
        saved_state = request.session.get("oauth_state")
        saved_code_verifier = request.session.get("code_verifier")

        if not saved_state or not saved_code_verifier:
            raise HTTPException(status_code=400, detail="OAuth session data missing.")
        if state != saved_state:
            raise HTTPException(status_code=400, detail="OAuth state mismatch.")

        flow = create_flow(state=saved_state)
        flow.code_verifier = saved_code_verifier
        flow.fetch_token(code=code)
        creds = flow.credentials

        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        info = google_id_token.verify_oauth2_token(
            creds.id_token, google_requests.Request(), client_id(), clock_skew_in_seconds=10
        )
        sub = info["sub"]

        user = upsert_google_user(sub, info.get("email"), info.get("name"))
        save_user_tokens(sub, creds)

        request.session.pop("oauth_state", None)
        request.session.pop("code_verifier", None)

        response = RedirectResponse(f"{settings.frontend_origin}?google_connected=true")
        _set_session_cookie(response, user.id)
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("google auth callback failed")
        raise HTTPException(status_code=500, detail="Google authorization failed.")


@app.post("/auth/guest")
def auth_guest(response: Response):
    user = create_guest_user()
    _set_session_cookie(response, user.id)
    return {"id": user.id, "is_guest": True, "email": None, "name": None}


@app.get("/auth/me")
def auth_me(user: User | None = Depends(current_user_optional)):
    if user is None:
        return {"user": None}
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_guest": user.is_guest,
            "google_connected": user.can_use_google,
        }
    }


@app.post("/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(session.COOKIE_NAME)
    return {"ok": True}


@app.post("/auth/disconnect-google")
def auth_disconnect_google(user: User = Depends(current_user)):
    delete_user_tokens(user.id)
    return {"ok": True}


# ------------------------------------------------------------------ chat

def _thread_id(user: User, conversation_id: str) -> str:
    return f"{user.id}::{conversation_id or 'default'}"


def _run_graph(user: User, conversation_id: str, payload) -> dict:
    """Invoke the assistant graph, mapping errors to a friendly reply instead of a 500."""
    config = {"configurable": {"thread_id": _thread_id(user, conversation_id)}}
    try:
        with user_scope(user.id):
            return graph.invoke(payload, config=config)
    except RuntimeError as e:
        logger.warning("graph runtime error for user=%s: %s", user.id, e)
        return {"reply": str(e), "intent": "error", "tool_used": None}
    except Exception:
        logger.exception("graph failed for user=%s", user.id)
        return {
            "reply": "Something went wrong while handling that request. Please try again.",
            "intent": "error",
            "tool_used": None,
        }


def _build_chat_response(result: dict) -> ChatResponse:
    if result.get("approval_required") and result.get("approval_payload"):
        return ChatResponse(
            reply="Approval required before I take this action.",
            intent=result.get("intent", "draft_email"),
            tool_used="approval",
            requires_approval=True,
            approval_payload=result.get("approval_payload"),
        )

    if "__interrupt__" in result:
        interrupts = result["__interrupt__"] or []
        interrupt_value = getattr(interrupts[0], "value", None) if interrupts else None
        return ChatResponse(
            reply="Approval required before I take this action.",
            intent=result.get("intent", "draft_email"),
            tool_used="approval",
            requires_approval=True,
            approval_payload=interrupt_value,
        )

    return ChatResponse(
        reply=result.get("reply", "No reply generated."),
        intent=result.get("intent", "unknown"),
        tool_used=result.get("tool_used"),
        requires_approval=False,
        approval_payload=None,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: User = Depends(current_user)):
    result = _run_graph(user, req.user_id, {"user_id": user.id, "message": req.message})
    logger.debug("graph result: %s", result)
    return _build_chat_response(result)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# Graph nodes whose LLM tokens should be forwarded to the SSE client.
_STREAMING_NODES = {"chat_response", "history_response"}


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, user: User = Depends(current_user)):
    """Same as /chat, but streams the assistant's conversational reply token by
    token over Server-Sent Events. Tool results and approval payloads arrive in a
    single terminal `final` event."""

    config = {"configurable": {"thread_id": _thread_id(user, req.user_id)}}

    def gen():
        final_state: dict = {}
        try:
            with user_scope(user.id):
                for mode, chunk in graph.stream(
                    {"user_id": user.id, "message": req.message},
                    config=config,
                    stream_mode=["messages", "values"],
                ):
                    if mode == "messages":
                        msg, meta = chunk
                        if meta.get("langgraph_node") in _STREAMING_NODES:
                            token = getattr(msg, "content", "")
                            if token:
                                yield _sse({"type": "token", "content": token})
                    elif mode == "values":
                        final_state = chunk
        except RuntimeError as e:
            logger.warning("stream runtime error for user=%s: %s", user.id, e)
            yield _sse({"type": "final", **ChatResponse(
                reply=str(e), intent="error", requires_approval=False).model_dump()})
            return
        except Exception:
            logger.exception("stream failed for user=%s", user.id)
            yield _sse({"type": "final", **ChatResponse(
                reply="Something went wrong. Please try again.", intent="error",
                requires_approval=False).model_dump()})
            return

        snapshot = graph.get_state(config)
        if snapshot.tasks:
            interrupts = [i for t in snapshot.tasks for i in (t.interrupts or [])]
            if interrupts:
                final_state = {**final_state, "__interrupt__": interrupts}

        yield _sse({"type": "final", **_build_chat_response(final_state).model_dump()})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/chat/approve", response_model=ChatResponse)
def chat_approve(req: ApprovalRequest, user: User = Depends(current_user)):
    result = _run_graph(user, req.user_id, Command(resume={"approved": req.approved}))
    logger.debug("approval result: %s", result)

    return ChatResponse(
        reply=result.get("reply", "Approval handled."),
        intent=result.get("intent", "approval"),
        tool_used=result.get("tool_used"),
        requires_approval=False,
        approval_payload=None,
    )


# ------------------------------------------------------------------ history / RAG

@app.get("/history/status")
def history_status(user: User = Depends(current_user)):
    return {"user_id": user.id, "indexed_chunks": get_store().count(user.id)}


@app.post("/history/index")
def history_index(req: HistoryIndexRequest, user: User = Depends(current_user)):
    """Pull recent Gmail, embed it, and upsert into the retrieval store.
    Synchronous and bounded (default 200 messages)."""
    if user.is_guest:
        raise HTTPException(status_code=403, detail="Sign in with Google to index your email.")
    try:
        touch_user(user.id)
        with user_scope(user.id):
            stats = ingest_user_history(
                user.id,
                max_messages=req.max_messages,
                query=req.query,
                reindex=req.reindex,
            )
        return {"status": "ok", **stats}
    except RuntimeError as e:
        logger.warning("history index failed for user=%s: %s", user.id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("history index crashed for user=%s", user.id)
        raise HTTPException(status_code=500, detail="History indexing failed.")
