from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from langgraph.types import Command

from models.schemas import ChatRequest, ChatResponse, ApprovalRequest
from graph.assistant_graph import build_graph
from graph.memory import init_memory
from integrations.google_auth import create_flow, save_tokens
from config import settings

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
    secret_key="super-secret-dev-key-change-this-later",
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        save_tokens(creds)

        request.session.pop("oauth_state", None)
        request.session.pop("code_verifier", None)

        return RedirectResponse(f"{settings.frontend_origin}?google_connected=true")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        config = {"configurable": {"thread_id": req.user_id}}

        result = graph.invoke(
            {
                "user_id": req.user_id,
                "message": req.message,
            },
            config=config,
        )

        print("GRAPH RESULT:", result)

        # Practical approval detection
        if result.get("approval_required") and result.get("approval_payload"):
            return ChatResponse(
                reply="Approval required before I create the draft.",
                intent=result.get("intent", "draft_email"),
                tool_used="approval",
                requires_approval=True,
                approval_payload=result.get("approval_payload"),
            )

        # Optional support if LangGraph returns __interrupt__
        if "__interrupt__" in result:
            interrupts = result["__interrupt__"]
            interrupt_value = None

            if interrupts:
                first_interrupt = interrupts[0]
                interrupt_value = getattr(first_interrupt, "value", first_interrupt)

            return ChatResponse(
                reply="Approval required before I create the draft.",
                intent="draft_email",
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/approve", response_model=ChatResponse)
def chat_approve(req: ApprovalRequest):
    try:
        config = {"configurable": {"thread_id": req.user_id}}

        result = graph.invoke(
            Command(resume={"approved": req.approved}),
            config=config,
        )

        print("APPROVAL RESULT:", result)

        return ChatResponse(
            reply=result.get("reply", "Approval handled."),
            intent=result.get("intent", "approval"),
            tool_used=result.get("tool_used"),
            requires_approval=False,
            approval_payload=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))