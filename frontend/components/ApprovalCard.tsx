"use client";

function formatDateTime(value?: string) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

type ApprovalCardProps = {
  payload: any;
  onApprove: () => void;
  onReject: () => void;
  loading?: boolean;
  resolvedStatus?: "approved" | "rejected" | null;
};

export default function ApprovalCard({
  payload,
  onApprove,
  onReject,
  loading = false,
  resolvedStatus = null,
}: ApprovalCardProps) {
  const actionType = payload?.action_type;
  const risk = payload?.risk_level;
  const reason = payload?.reason;

  const innerPayload = payload?.payload || {};
  const action = innerPayload?.action;

  const draft = innerPayload?.draft;
  const event = innerPayload?.event;

  const conflicts = payload?.conflict_details || [];
  const suggestedEvent = payload?.suggested_event;

  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-amber-900">
            Approval Required
          </h3>
          <p className="text-xs text-slate-600">
            {actionType} • {risk?.toUpperCase()}
          </p>
        </div>

        {resolvedStatus === "approved" && (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
            Approved
          </span>
        )}

        {resolvedStatus === "rejected" && (
          <span className="rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700">
            Rejected
          </span>
        )}
      </div>

      {/* Reason */}
      {reason && (
        <div className="mb-3 rounded-xl bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
          {reason}
        </div>
      )}

      {/* EMAIL DRAFT */}
      {action === "create_gmail_draft" && (
        <div className="space-y-2 rounded-xl bg-white p-4 text-sm shadow-sm">
          <p><b>To:</b> {draft?.to || "-"}</p>
          <p><b>Subject:</b> {draft?.subject || "-"}</p>
          <p><b>Body:</b> {draft?.body || "-"}</p>
        </div>
      )}

      {/* EMAIL REPLY */}
      {action === "create_gmail_reply_draft" && (
        <div className="space-y-2 rounded-xl bg-white p-4 text-sm shadow-sm">
          <p><b>To:</b> {draft?.to || "-"}</p>
          <p><b>Subject:</b> {draft?.subject || "-"}</p>
          <p><b>Reply:</b> {draft?.body || "-"}</p>
        </div>
      )}

      {/* CALENDAR EVENT */}
      {action === "create_calendar_event" && (
        <div className="space-y-3 rounded-xl bg-white p-4 text-sm shadow-sm">
          <div>
            <p><b>Title:</b> {event?.summary || suggestedEvent?.summary}</p>
            <p><b>Start:</b> {formatDateTime(event?.start || suggestedEvent?.start)}</p>
            <p><b>End:</b> {formatDateTime(event?.end || suggestedEvent?.end)}</p>
            <p>
              <span className="font-medium text-slate-900">Timezone:</span>{" "}
              {payload?.timezone || "Local time"}
            </p>
            <p>
              <span className="font-medium text-slate-900">Conference:</span>{" "}
              {(event?.conference_type || suggestedEvent?.conference_type) === "google_meet"
                ? "Google Meet"
                : "None"}
            </p>
          </div>

          {/* Conflict Section */}
          {conflicts.length > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3">
              <p className="text-xs font-semibold text-rose-600 mb-2">
                Conflicting Events
              </p>

              {conflicts.map((c: any, i: number) => (
                <div key={i} className="mb-2">
                  <div className="font-medium">{c.summary}</div>
                  <div className="text-xs">
                    {formatDateTime(c.start)} — {formatDateTime(c.end)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Suggested Event */}
          {suggestedEvent && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-xs font-semibold text-emerald-600 mb-2">
                Suggested Time
              </p>

              <p><b>Start:</b> {formatDateTime(suggestedEvent.start)}</p>
              <p><b>End:</b> {formatDateTime(suggestedEvent.end)}</p>
            </div>
          )}
        </div>
      )}

      {/* Buttons */}
      {!resolvedStatus && (
        <div className="mt-4 flex gap-3">
          <button
            onClick={onApprove}
            disabled={loading}
            className="rounded-xl bg-emerald-600 px-4 py-2 text-white text-sm hover:bg-emerald-700"
          >
            {loading ? "Processing..." : "Approve"}
          </button>

          <button
            onClick={onReject}
            disabled={loading}
            className="rounded-xl bg-rose-600 px-4 py-2 text-white text-sm hover:bg-rose-700"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}