/**
 * Recommendation card — a `request_confirmation` interaction from an analyst agent.
 * Hero surface (offset shadow). Inline approve/reject with cited context docs.
 * Reflects issue_interactions rows per [[../architecture/agent-runtime]] §Recommendation Surfacing.
 * Tokens: --amber, --rust, --ink, --cream-light, --moss, --honey
 * See [[design-system/components/recommendation-card]]
 */
"use client";

import * as React from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { Sparkles, FileText, Check, X, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CitedContext {
  path: string;
  commitSha: string;
  relevance: string;
}

export interface RecommendationCardData {
  id: string;
  agentName: string;
  prompt: string;
  summary: string;
  acceptLabel?: string;
  rejectLabel?: string;
  rejectRequiresReason?: boolean;
  citedContext?: CitedContext[];
  createdAt: Date | string;
  /** Optional payload action button (e.g., "View proposed rotation slate") */
  detailLabel?: string;
}

export interface RecommendationCardProps extends Omit<React.HTMLAttributes<HTMLElement>, "onSubmit"> {
  recommendation: RecommendationCardData;
  onAccept?: (id: string) => void | Promise<void>;
  onReject?: (id: string, reason?: string) => void | Promise<void>;
  onViewDetail?: (id: string) => void;
  onOpenCitation?: (path: string, commitSha: string) => void;
  disabled?: boolean;
}

const RecommendationCard = React.forwardRef<HTMLElement, RecommendationCardProps>(
  (
    {
      className,
      recommendation,
      onAccept,
      onReject,
      onViewDetail,
      onOpenCitation,
      disabled,
      ...props
    },
    ref
  ) => {
    const [rejecting, setRejecting] = React.useState(false);
    const [reason, setReason] = React.useState("");
    const [pending, setPending] = React.useState<"accept" | "reject" | null>(null);
    const [citationsOpen, setCitationsOpen] = React.useState(false);

    const acceptLabel = recommendation.acceptLabel ?? "Approve";
    const rejectLabel = recommendation.rejectLabel ?? "Reject";
    const createdRel = formatDistanceToNowStrict(
      typeof recommendation.createdAt === "string"
        ? new Date(recommendation.createdAt)
        : recommendation.createdAt,
      { addSuffix: true }
    );

    const handleAccept = async () => {
      if (!onAccept) return;
      setPending("accept");
      try {
        await onAccept(recommendation.id);
      } finally {
        setPending(null);
      }
    };

    const handleReject = async () => {
      if (!onReject) return;
      if (recommendation.rejectRequiresReason && !rejecting) {
        setRejecting(true);
        return;
      }
      if (recommendation.rejectRequiresReason && !reason.trim()) {
        return;
      }
      setPending("reject");
      try {
        await onReject(recommendation.id, reason.trim() || undefined);
      } finally {
        setPending(null);
        setRejecting(false);
        setReason("");
      }
    };

    const isPending = pending !== null;

    return (
      <article
        ref={ref}
        className={cn(
          "flex flex-col gap-5 p-6 rounded-xl bg-card text-card-foreground",
          "border-[1.5px] border-border-bold shadow-flat",
          className
        )}
        aria-busy={isPending}
        {...props}
      >
        {/* Header */}
        <header className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-flex items-center justify-center h-6 w-6 rounded-sm bg-amber text-ink border-[1.5px] border-ink">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
            <span className="font-medium">{recommendation.agentName}</span>
            <span className="text-ink-soft">recommends</span>
          </div>
          <time className="font-mono text-xs text-ink-soft shrink-0">
            {createdRel}
          </time>
        </header>

        {/* Prompt + summary */}
        <div className="space-y-2">
          <h3 className="text-2xl text-foreground">{recommendation.prompt}</h3>
          <p className="text-base text-foreground/90 leading-relaxed">
            {recommendation.summary}
          </p>
        </div>

        {/* View detail link */}
        {recommendation.detailLabel && onViewDetail && (
          <button
            type="button"
            onClick={() => onViewDetail(recommendation.id)}
            className="self-start inline-flex items-center gap-1.5 text-sm font-medium text-copper hover:underline focus-visible:underline"
          >
            {recommendation.detailLabel}
            <ChevronDown className="h-3.5 w-3.5 -rotate-90" aria-hidden="true" />
          </button>
        )}

        {/* Cited context */}
        {recommendation.citedContext && recommendation.citedContext.length > 0 && (
          <section className="rounded-md bg-muted/60 border border-border p-3">
            <button
              type="button"
              onClick={() => setCitationsOpen((v) => !v)}
              aria-expanded={citationsOpen}
              className="flex w-full items-center justify-between gap-2 text-xs font-medium text-ink-soft"
            >
              <span className="inline-flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                Cited context · {recommendation.citedContext.length} doc
                {recommendation.citedContext.length === 1 ? "" : "s"}
              </span>
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  citationsOpen && "rotate-180"
                )}
                aria-hidden="true"
              />
            </button>

            {citationsOpen && (
              <ul className="mt-2 space-y-1.5">
                {recommendation.citedContext.map((cite) => (
                  <li
                    key={`${cite.path}-${cite.commitSha}`}
                    className="flex items-center justify-between gap-3 text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenCitation?.(cite.path, cite.commitSha)}
                      className="font-mono text-ink hover:underline focus-visible:underline truncate text-left"
                    >
                      {cite.path}
                    </button>
                    <span className="text-ink-soft shrink-0">{cite.relevance}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* Reject reason (when required) */}
        {rejecting && (
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-ink-soft" htmlFor={`reject-reason-${recommendation.id}`}>
              Reason for rejection
            </label>
            <textarea
              id={`reject-reason-${recommendation.id}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className="w-full rounded-md border-[1.5px] border-border bg-background p-2 text-sm focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              placeholder="Required so the agent learns from the rejection…"
            />
          </div>
        )}

        {/* Actions */}
        <footer className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={handleReject}
            disabled={disabled || isPending}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
              "bg-transparent text-ink border-[1.5px] border-border-bold",
              "hover:bg-muted focus-visible:bg-muted",
              "disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            )}
          >
            <X className="h-4 w-4" aria-hidden="true" />
            {rejecting ? "Confirm rejection" : rejectLabel}
          </button>
          <button
            type="button"
            onClick={handleAccept}
            disabled={disabled || isPending || rejecting}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
              "bg-amber text-ink border-[1.5px] border-border-bold",
              "hover:shadow-flat-sm focus-visible:shadow-flat-sm",
              "disabled:opacity-50 disabled:cursor-not-allowed transition-shadow"
            )}
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            {acceptLabel}
          </button>
        </footer>
      </article>
    );
  }
);
RecommendationCard.displayName = "RecommendationCard";

export { RecommendationCard };
