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
  const action = payload?.action;
  const note = payload?.note;
  const conflicts = payload?.conflicts || [];
  const emailContext = payload?.email_context;

  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          <h3 className="text-sm font-semibold text-amber-900">
            Approval Required
          </h3>
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

      {note && (
        <div className="mb-3 rounded-xl bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
          {note}
        </div>
      )}

      {action === "create_gmail_draft" && (
        <div className="space-y-2 rounded-xl bg-white p-4 text-sm text-slate-700 shadow-sm">
          <p>
            <span className="font-medium text-slate-900">Action:</span>{" "}
            Create Gmail Draft
          </p>
          <p>
            <span className="font-medium text-slate-900">To:</span>{" "}
            {payload?.draft?.to || "-"}
          </p>
          <p>
            <span className="font-medium text-slate-900">Subject:</span>{" "}
            {payload?.draft?.subject || "-"}
          </p>
          <p>
            <span className="font-medium text-slate-900">Body:</span>{" "}
            {payload?.draft?.body || "-"}
          </p>
        </div>
      )}

      {action === "create_gmail_reply_draft" && (
        <div className="space-y-3 rounded-xl bg-white p-4 text-sm text-slate-700 shadow-sm">
          <div className="space-y-1">
            <p>
              <span className="font-medium text-slate-900">Action:</span>{" "}
              Create Reply Draft
            </p>
            <p>
              <span className="font-medium text-slate-900">To:</span>{" "}
              {payload?.draft?.to || "-"}
            </p>
            <p>
              <span className="font-medium text-slate-900">Subject:</span>{" "}
              {payload?.draft?.subject || "-"}
            </p>
          </div>

          {emailContext && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Original Email Context
              </p>
              <p>
                <span className="font-medium text-slate-900">From:</span>{" "}
                {emailContext.sender || "-"}
              </p>
              <p>
                <span className="font-medium text-slate-900">Subject:</span>{" "}
                {emailContext.subject || "-"}
              </p>
              <p>
                <span className="font-medium text-slate-900">Snippet:</span>{" "}
                {emailContext.snippet || "-"}
              </p>
            </div>
          )}

          <div>
            <p className="mb-1 font-medium text-slate-900">Reply Body:</p>
            <p>{payload?.draft?.body || "-"}</p>
          </div>
        </div>
      )}

      {action === "create_calendar_event" && (
        <div className="space-y-3 rounded-xl bg-white p-4 text-sm text-slate-700 shadow-sm">
          <div className="space-y-1">
            <p>
              <span className="font-medium text-slate-900">Action:</span>{" "}
              Create Calendar Event
            </p>
            <p>
              <span className="font-medium text-slate-900">Title:</span>{" "}
              {payload?.event?.summary || "-"}
            </p>
            <p>
              <span className="font-medium text-slate-900">Start:</span>{" "}
              {formatDateTime(payload?.event?.start)}
            </p>
            <p>
              <span className="font-medium text-slate-900">End:</span>{" "}
              {formatDateTime(payload?.event?.end)}
            </p>
          </div>

          {conflicts.length > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-600">
                Conflicting Events
              </p>
              <div className="space-y-2">
                {conflicts.map((conflict: any, idx: number) => (
                  <div key={idx} className="text-sm text-slate-700">
                    <div className="font-medium text-slate-900">
                      {conflict.summary}
                    </div>
                    <div>
                      {formatDateTime(conflict.start)} —{" "}
                      {formatDateTime(conflict.end)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!resolvedStatus && (
        <div className="mt-4 flex gap-3">
          <button
            onClick={onApprove}
            disabled={loading}
            className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? "Processing..." : "Approve"}
          </button>

          <button
            onClick={onReject}
            disabled={loading}
            className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-700 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}