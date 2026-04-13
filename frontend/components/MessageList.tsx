import ApprovalCard from "./ApprovalCard";

export type Message = {
  role: "user" | "assistant";
  text: string;
  requiresApproval?: boolean;
  approvalPayload?: any;
  approvalResolved?: boolean;
  approvalStatus?: "approved" | "rejected" | null;
};

type MessageListProps = {
  messages: Message[];
  onApprove: () => void;
  onReject: () => void;
  approvalLoading?: boolean;
};

export default function MessageList({
  messages,
  onApprove,
  onReject,
  approvalLoading = false,
}: MessageListProps) {
  return (
    <div className="space-y-5">
      {messages.map((msg, idx) => {
        const isUser = msg.role === "user";

        return (
          <div
            key={idx}
            className={`flex ${isUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-3xl px-5 py-4 shadow-sm ${
                isUser
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-200 bg-slate-50 text-slate-800"
              }`}
            >
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide opacity-70">
                {isUser ? "You" : "Assistant"}
              </div>

              <p className="whitespace-pre-wrap text-sm leading-6">{msg.text}</p>

              {!isUser && msg.requiresApproval && msg.approvalPayload && (
                <ApprovalCard
                  payload={msg.approvalPayload}
                  onApprove={onApprove}
                  onReject={onReject}
                  loading={approvalLoading}
                  resolvedStatus={msg.approvalStatus ?? null}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}