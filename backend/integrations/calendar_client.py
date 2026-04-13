from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from integrations.google_auth import load_tokens

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def get_calendar_service():
    creds = load_tokens()
    if not creds:
        raise RuntimeError("Google account not connected.")
    return build("calendar", "v3", credentials=creds)


def _ensure_rfc3339(dt_str: str) -> str:
    """
    Convert an ISO datetime string into RFC3339 with timezone offset.
    If the datetime is naive, assume America/Los_Angeles.
    """
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.isoformat()


def get_today_events(max_results: int = 10):
    service = get_calendar_service()

    now = datetime.now(LOCAL_TZ)
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ)
    end_of_day = start_of_day + timedelta(days=1)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    output = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        output.append({
            "summary": event.get("summary", "(No Title)"),
            "start": start,
            "end": end,
        })

    return output


def create_calendar_event(summary: str, start_iso: str, end_iso: str):
    service = get_calendar_service()

    start_rfc3339 = _ensure_rfc3339(start_iso)
    end_rfc3339 = _ensure_rfc3339(end_iso)

    event_body = {
        "summary": summary,
        "start": {
            "dateTime": start_rfc3339,
            "timeZone": "America/Los_Angeles",
        },
        "end": {
            "dateTime": end_rfc3339,
            "timeZone": "America/Los_Angeles",
        },
    }

    event = service.events().insert(
        calendarId="primary",
        body=event_body,
    ).execute()

    return {
        "id": event.get("id"),
        "htmlLink": event.get("htmlLink"),
        "summary": event.get("summary"),
    }


def get_events_in_range(start_iso: str, end_iso: str):
    service = get_calendar_service()

    start_rfc3339 = _ensure_rfc3339(start_iso)
    end_rfc3339 = _ensure_rfc3339(end_iso)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_rfc3339,
        timeMax=end_rfc3339,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    output = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        output.append({
            "summary": event.get("summary", "(No Title)"),
            "start": start,
            "end": end,
        })

    return output