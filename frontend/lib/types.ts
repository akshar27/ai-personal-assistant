export interface EmailDraft {
  to?: string;
  subject?: string;
  body?: string;
}

export interface CalendarEventDraft {
  summary?: string;
  start?: string;
  end?: string;
  conference_type?: "none" | "google_meet";
}

export interface CalendarConflict {
  summary?: string;
  start?: string;
  end?: string;
}

export interface CalendarEvent {
  id?: string;
  summary?: string;
  start?: string;
  end?: string;
}

/** The inner `payload` produced by the graph's `action_payload`. */
export interface ActionPayload {
  action?:
    | "create_gmail_draft"
    | "create_gmail_reply_draft"
    | "create_calendar_event"
    | "send_gmail_message"
    | "delete_calendar_event";
  draft?: EmailDraft;
  email?: EmailDraft; // for send_gmail_message
  event?: CalendarEventDraft | CalendarEvent;
  email_context?: { sender?: string; subject?: string; snippet?: string };
}

/** The full `approval_payload` returned on `requires_approval`. */
export interface ApprovalPayload {
  action_type?: string;
  risk_level?: "low" | "medium" | "high" | "";
  reason?: string;
  timezone?: string;
  payload?: ActionPayload;
  conflict_found?: boolean;
  conflict_details?: CalendarConflict[];
  suggested_event?: CalendarEventDraft;
}
