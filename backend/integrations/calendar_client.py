from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from integrations.google_auth import load_tokens
import uuid

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def get_calendar_service():
    creds = load_tokens()
    if not creds:
        raise RuntimeError("Google account not connected.")
    return build("calendar", "v3", credentials=creds)


def _ensure_rfc3339(dt_str: str, timezone_str: str = "America/Los_Angeles") -> str:
    dt = datetime.fromisoformat(dt_str)
    tz = ZoneInfo(timezone_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
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

        meet_link = None
        conference_data = event.get("conferenceData", {})
        entry_points = conference_data.get("entryPoints", [])
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                meet_link = entry.get("uri")
                break

        output.append({
            "summary": event.get("summary", "(No Title)"),
            "start": start,
            "end": end,
            "meetLink": meet_link,
        })

    return output


def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    conference_type: str = "none",
    timezone_str: str = "America/Los_Angeles",
):
    service = get_calendar_service()

    start_rfc3339 = _ensure_rfc3339(start_iso, timezone_str)
    end_rfc3339 = _ensure_rfc3339(end_iso, timezone_str)

    event_body = {
        "summary": summary,
        "start": {
            "dateTime": start_rfc3339,
            "timeZone": timezone_str,
        },
        "end": {
            "dateTime": end_rfc3339,
            "timeZone": timezone_str,
        },
    }

    insert_kwargs = {
        "calendarId": "primary",
        "body": event_body,
    }

    if conference_type == "google_meet":
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {
                    "type": "hangoutsMeet"
                },
            }
        }
        insert_kwargs["conferenceDataVersion"] = 1

    event = service.events().insert(**insert_kwargs).execute()

    meet_link = None
    conference_data = event.get("conferenceData", {})
    entry_points = conference_data.get("entryPoints", [])
    for entry in entry_points:
        if entry.get("entryPointType") == "video":
            meet_link = entry.get("uri")
            break

    return {
        "id": event.get("id"),
        "htmlLink": event.get("htmlLink"),
        "summary": event.get("summary"),
        "meetLink": meet_link,
    }


def get_events_in_range(
    start_iso: str,
    end_iso: str,
    timezone_str: str = "America/Los_Angeles",
):
    service = get_calendar_service()

    start_rfc3339 = _ensure_rfc3339(start_iso, timezone_str)
    end_rfc3339 = _ensure_rfc3339(end_iso, timezone_str)

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

def get_upcoming_events(
    max_results: int = 5,
    timezone_str: str = "America/Los_Angeles",
):
    service = get_calendar_service()

    tz = ZoneInfo(timezone_str)
    now = datetime.now(ZoneInfo(timezone_str))
    future = now + timedelta(days=7)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=future.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    output = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))

        meet_link = None
        conference_data = event.get("conferenceData", {})
        entry_points = conference_data.get("entryPoints", [])
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                meet_link = entry.get("uri")
                break

        output.append({
            "id": event.get("id"),
            "summary": event.get("summary", "(No Title)"),
            "start": start,
            "end": end,
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "htmlLink": event.get("htmlLink"),
            "meetLink": meet_link,
            "attendees": [
                attendee.get("email")
                for attendee in event.get("attendees", [])
                if attendee.get("email")
            ],
        })

    return output