import json
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from langgraph.types import Command

from models.schemas import ChatRequest, ChatResponse, ApprovalRequest
from graph.assistant_graph import build_graph
from graph.memory import init_memory
from integrations.google_auth import create_flow, save_tokens
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/google/start")
def auth_google_start(request: Request):
    try:
        flow = create_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
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
        save_tokens(flow.credentials)

        request.session.pop("oauth_state", None)
        request.session.pop("code_verifier", None)

        return RedirectResponse(f"{settings.frontend_origin}?google_connected=true")
    except HTTPException:
        raise
    except Exception:
        logger.exception("google auth callback failed")
        raise HTTPException(status_code=500, detail="Google authorization failed.")


def _run_graph(user_id: str, payload) -> dict:
    """Invoke the assistant graph, mapping errors to a friendly reply instead of a 500."""
    config = {"configurable": {"thread_id": user_id}}
    try:
        return graph.invoke(payload, config=config)
    except RuntimeError as e:
        # Integration-level problems (e.g. Google not connected) — safe to surface.
        logger.warning("graph runtime error for user=%s: %s", user_id, e)
        return {"reply": str(e), "intent": "error", "tool_used": None}
    except Exception:
        logger.exception("graph failed for user=%s", user_id)
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
def chat(req: ChatRequest):
    result = _run_graph(req.user_id, {"user_id": req.user_id, "message": req.message})
    logger.debug("graph result: %s", result)
    return _build_chat_response(result)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Same as /chat, but streams the assistant's conversational reply token by
    token over Server-Sent Events. Tool results and approval payloads arrive in a
    single terminal `final` event."""

    def gen():
        config = {"configurable": {"thread_id": req.user_id}}
        final_state: dict = {}
        try:
            for mode, chunk in graph.stream(
                {"user_id": req.user_id, "message": req.message},
                config=config,
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    msg, meta = chunk
                    if meta.get("langgraph_node") == "chat_response":
                        token = getattr(msg, "content", "")
                        if token:
                            yield _sse({"type": "token", "content": token})
                elif mode == "values":
                    final_state = chunk
        except RuntimeError as e:
            logger.warning("stream runtime error for user=%s: %s", req.user_id, e)
            yield _sse({"type": "final", **ChatResponse(
                reply=str(e), intent="error", requires_approval=False).model_dump()})
            return
        except Exception:
            logger.exception("stream failed for user=%s", req.user_id)
            yield _sse({"type": "final", **ChatResponse(
                reply="Something went wrong. Please try again.", intent="error",
                requires_approval=False).model_dump()})
            return

        # merge interrupt info (present on the state snapshot after a pause)
        snapshot = graph.get_state(config)
        if snapshot.tasks:
            interrupts = [i for t in snapshot.tasks for i in (t.interrupts or [])]
            if interrupts:
                final_state = {**final_state, "__interrupt__": interrupts}

        yield _sse({"type": "final", **_build_chat_response(final_state).model_dump()})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/chat/approve", response_model=ChatResponse)
def chat_approve(req: ApprovalRequest):
    result = _run_graph(req.user_id, Command(resume={"approved": req.approved}))
    logger.debug("approval result: %s", result)

    return ChatResponse(
        reply=result.get("reply", "Approval handled."),
        intent=result.get("intent", "approval"),
        tool_used=result.get("tool_used"),
        requires_approval=False,
        approval_payload=None,
    )
