from pydantic import BaseModel, Field
from typing import Optional, Any, List


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
    conference_type: str = Field(
        default="none",
        description='Conference type requested by the user. Allowed values: none or google_meet.'
    )


class EmailReplyExtraction(BaseModel):
    body: str = Field(description="Reply email body")

    

class DailyBriefingExtraction(BaseModel):
    email_summary: str = Field(description="Short summary of important unread emails")
    calendar_summary: str = Field(description="Short summary of today's calendar")
    priorities: str = Field(description="Top priorities or recommended next actions for today")
    overall_brief: str = Field(description="A concise combined daily briefing for the user")

class TaskExtraction(BaseModel):
    title: str = Field(description="Short task or reminder title")
    due_at: str = Field(
        default="",
        description="Due datetime in ISO format. Empty string if no due time is provided."
    )
    source: str = Field(
        default="manual",
        description="Task source or type, such as manual, follow_up, job_search, email, calendar"
    )

class MeetingPrepExtraction(BaseModel):
    meeting_summary: str
    context: str
    talking_points: List[str]
    suggested_actions: List[str]


class ChatReply(BaseModel):
    reply: str = Field(description="A helpful, concise conversational reply to the user.")


class EmailSendExtraction(BaseModel):
    to: str = Field(description="Recipient email address. Empty string if not provided.")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body text")


class EventMatchExtraction(BaseModel):
    """Which of the listed upcoming events the user wants to cancel/delete."""
    match_index: int = Field(
        description="1-based index of the matching event in the provided list, "
        "or 0 if none clearly match."
    )
    reason: str = Field(default="", description="Why this event was chosen.")