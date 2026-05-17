/**
 * InteractionCard — paperclip request_confirmation surface on a task.
 * Bold-shadow hero card with Approve/Reject buttons.
 */
"use client";

import * as React from "react";
import { format, formatDistanceToNowStrict } from "date-fns";
import { Sparkles, Check, X, FileText, ChevronDown, CheckCircle2, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskInteraction } from "@/lib/types";

export interface InteractionCardProps {
  interaction: TaskInteraction;
  /** Resolved actor name (agent or operator). */
  actorName?: string;
  /** Decision handler. Disabled when status is not pending. */
  onDecide?: (decision: "approve" | "reject", reason?: string) => Promise<void> | void;
  className?: string;
}

export function InteractionCard({
  interaction,
  actorName,
  onDecide,
  className,
}: InteractionCardProps) {
  const isPending = interaction.status === "pending";
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [pending, setPending] = React.useState<"approve" | "reject" | null>(null);
  const [citationsOpen, setCitationsOpen] = React.useState(false);

  const p = interaction.payload;
  const prompt = (p?.prompt as string | undefined) ?? "Approval requested";
  const summary = p?.summary as string | undefined;
  const acceptLabel = (p?.acceptLabel as string | undefined) ?? "Approve";
  const rejectLabel = (p?.rejectLabel as string | undefined) ?? "Reject";
  const rejectRequiresReason = Boolean(p?.rejectRequiresReason);
  const cited = (p?.citedContext as Array<{ path: string; commitSha?: string; relevance?: string }> | undefined) ?? [];

  const handleAccept = async () => {
    if (!onDecide) return;
    setPending("approve");
    try {
      await onDecide("approve");
    } finally {
      setPending(null);
    }
  };

  const handleReject = async () => {
    if (!onDecide) return;
    if (rejectRequiresReason && !rejecting) {
      setRejecting(true);
      return;
    }
    if (rejectRequiresReason && !reason.trim()) return;
    setPending("reject");
    try {
      await onDecide("reject", reason.trim() || undefined);
    } finally {
      setPending(null);
      setRejecting(false);
      setReason("");
    }
  };

  const statusBadge = (() => {
    if (interaction.status === "approved")
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-moss">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Approved
        </span>
      );
    if (interaction.status === "rejected")
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-rust">
          <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> Rejected
        </span>
      );
    if (interaction.status === "expired" || interaction.status === "superseded")
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-soft">
          <Clock className="h-3.5 w-3.5" aria-hidden="true" /> {interaction.status}
        </span>
      );
    return null;
  })();

  return (
    <article
      className={cn(
        "flex flex-col gap-4 p-5 rounded-xl bg-card text-card-foreground",
        "border-[1.5px] border-border-bold",
        isPending ? "shadow-flat" : "shadow-none opacity-90",
        className
      )}
      aria-busy={pending !== null}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="inline-flex items-center justify-center h-6 w-6 rounded-sm bg-amber text-ink border-[1.5px] border-ink">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <span className="font-medium">{actorName ?? "Agent"}</span>
          <span className="text-ink-soft">requests</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {statusBadge}
          <time
            className="font-mono text-xs text-ink-soft"
            title={format(new Date(interaction.createdAt), "yyyy-MM-dd HH:mm:ss")}
          >
            {formatDistanceToNowStrict(new Date(interaction.createdAt), { addSuffix: true })}
          </time>
        </div>
      </header>

      <div className="space-y-1.5">
        <h3 className="text-xl text-foreground">{prompt}</h3>
        {summary && (
          <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">{summary}</p>
        )}
      </div>

      {cited.length > 0 && (
        <section className="rounded-md bg-muted/60 border border-border p-3">
          <button
            type="button"
            onClick={() => setCitationsOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-2 text-xs font-medium text-ink-soft"
          >
            <span className="inline-flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" aria-hidden="true" />
              Cited context · {cited.length} doc{cited.length === 1 ? "" : "s"}
            </span>
            <ChevronDown
              className={cn("h-3.5 w-3.5 transition-transform", citationsOpen && "rotate-180")}
              aria-hidden="true"
            />
          </button>
          {citationsOpen && (
            <ul className="mt-2 space-y-1.5">
              {cited.map((c) => (
                <li
                  key={`${c.path}-${c.commitSha ?? "x"}`}
                  className="flex items-center justify-between gap-3 text-xs"
                >
                  <span className="font-mono text-ink truncate">{c.path}</span>
                  {c.relevance && (
                    <span className="text-ink-soft shrink-0">{c.relevance}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!isPending && interaction.decisionReason && (
        <div className="text-sm text-ink-soft border-l-2 border-rust pl-3">
          <span className="font-medium text-foreground">Reason:</span>{" "}
          {interaction.decisionReason}
        </div>
      )}

      {isPending && rejecting && (
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-ink-soft" htmlFor={`reason-${interaction.id}`}>
            Reason for rejection
          </label>
          <textarea
            id={`reason-${interaction.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className="w-full rounded-md border-[1.5px] border-border bg-background p-2 text-sm focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            placeholder="Required so the agent learns from the rejection…"
          />
        </div>
      )}

      {isPending && (
        <footer className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={handleReject}
            disabled={pending !== null}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
              "bg-transparent text-ink border-[1.5px] border-border-bold hover:bg-muted",
              "disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            )}
          >
            <X className="h-4 w-4" aria-hidden="true" />
            {rejecting ? "Confirm rejection" : rejectLabel}
          </button>
          <button
            type="button"
            onClick={handleAccept}
            disabled={pending !== null || rejecting}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
              "bg-amber text-ink border-[1.5px] border-border-bold",
              "hover:shadow-flat-sm focus-visible:shadow-flat-sm transition-shadow",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            {acceptLabel}
          </button>
        </footer>
      )}
    </article>
  );
}
