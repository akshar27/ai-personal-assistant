from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatRequest(BaseModel):
    user_id: str = Field(default="default_user")
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: str
    tool_used: Optional[str] = None
    requires_approval: bool = False
    approval_payload: Optional[Any] = None


class ApprovalRequest(BaseModel):
    user_id: str = Field(default="default_user")
    approved: bool


class EmailDraftExtraction(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body text")


class CalendarEventExtraction(BaseModel):
    summary: str = Field(description="Event title")
    start: str = Field(description="Start datetime in ISO format")
    end: str = Field(description="End datetime in ISO format")


class EmailReplyExtraction(BaseModel):
    body: str = Field(description="Reply email body")