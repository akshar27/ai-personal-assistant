import base64
from email.mime.text import MIMEText
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