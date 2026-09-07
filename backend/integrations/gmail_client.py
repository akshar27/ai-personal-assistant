import base64
import re
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

from googleapiclient.discovery import build
from integrations.google_auth import load_tokens


def get_gmail_service():
    creds = load_tokens()
    if not creds:
        raise RuntimeError("Google account not connected.")
    return build("gmail", "v1", credentials=creds)


def list_unread_emails(max_results: int = 5):
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q="is:unread",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    output = []

    for idx, msg in enumerate(messages, start=1):
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"]
        ).execute()

        headers = full_msg.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "(Unknown Sender)")
        snippet = full_msg.get("snippet", "")
        thread_id = full_msg.get("threadId")

        output.append({
            "index": idx,
            "id": msg["id"],
            "thread_id": thread_id,
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
        })

    return output


def get_email_by_id(message_id: str):
    service = get_gmail_service()

    full_msg = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    headers = full_msg.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "(Unknown Sender)")
    snippet = full_msg.get("snippet", "")
    thread_id = full_msg.get("threadId")

    return {
        "id": message_id,
        "thread_id": thread_id,
        "subject": subject,
        "sender": sender,
        "snippet": snippet,
    }


def gmail_link(message_id: str) -> str:
    return f"https://mail.google.com/mail/u/0/#all/{message_id}"


def _header(headers: list[dict], name: str, default: str = "") -> str:
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), default)


def _decode_part(data: str) -> str:
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def _extract_plain_body(payload: dict) -> str:
    """Walk the MIME tree and return the best plain-text representation."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime == "text/plain" and body_data:
        return _decode_part(body_data)
    if mime == "text/html" and body_data:
        return _strip_html(_decode_part(body_data))

    parts = payload.get("parts", []) or []
    # Prefer a text/plain part anywhere in the subtree; fall back to html.
    plain = [_extract_plain_body(p) for p in parts if p.get("mimeType", "").startswith("text/plain")]
    if any(plain):
        return "\n".join(p for p in plain if p).strip()
    collected = [_extract_plain_body(p) for p in parts]
    return "\n".join(p for p in collected if p).strip()


def list_message_ids(query: str = "newer_than:180d", max_results: int = 200) -> list[dict]:
    """Return [{id, thread_id}] for messages matching a Gmail search query,
    paging until `max_results` is reached."""
    service = get_gmail_service()
    out: list[dict] = []
    page_token = None

    while len(out) < max_results:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(100, max_results - len(out)),
            pageToken=page_token,
        ).execute()
        for m in resp.get("messages", []):
            out.append({"id": m["id"], "thread_id": m.get("threadId")})
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return out[:max_results]


def get_message_full(message_id: str) -> dict:
    """Fetch one message with its decoded plain-text body and a sent timestamp."""
    service = get_gmail_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    headers = msg.get("payload", {}).get("headers", [])
    date_raw = _header(headers, "Date")
    try:
        sent_at = parsedate_to_datetime(date_raw).astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    except (TypeError, ValueError):
        internal = msg.get("internalDate")
        sent_at = (
            datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
            if internal else ""
        )

    return {
        "id": message_id,
        "thread_id": msg.get("threadId"),
        "subject": _header(headers, "Subject", "(No Subject)"),
        "sender": _header(headers, "From", "(Unknown Sender)"),
        "sent_at": sent_at,
        "body": _extract_plain_body(msg.get("payload", {})),
    }


def send_gmail_message(to: str, subject: str, body: str):
    """Compose and send an email immediately (high-risk — only after approval)."""
    service = get_gmail_service()

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": sent.get("id"), "message": "Email sent."}


def create_gmail_draft(to: str, subject: str, body: str):
    service = get_gmail_service()

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    draft_body = {
        "message": {
            "raw": raw_message
        }
    }

    draft = service.users().drafts().create(
        userId="me",
        body=draft_body
    ).execute()

    return {
        "id": draft.get("id"),
        "message": "Draft created successfully."
    }


def create_gmail_reply_draft(thread_id: str, to: str, subject: str, body: str):
    service = get_gmail_service()

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = reply_subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    draft_body = {
        "message": {
            "threadId": thread_id,
            "raw": raw_message
        }
    }

    draft = service.users().drafts().create(
        userId="me",
        body=draft_body
    ).execute()

    return {
        "id": draft.get("id"),
        "message": "Reply draft created successfully."
    }