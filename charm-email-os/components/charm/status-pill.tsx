/**
 * Charm lifecycle status pill — domain/inbox/workspace state vocabulary.
 * Tokens: --moss, --sky, --sage, --ink-soft, --rust, --amber, --storm, --honey, --cream-light
 * See [[design-system/components/status-pill]] and [[design-system/tokens/colors]] §Charm Status Vocabulary
 */
"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const STATUS_KINDS = [
  "live",
  "incubating",
  "reserve",
  "dead",
  "burned",
  "kill-pending",
  "eod-scheduled",
  "disconnected",
  "drift",
  "quarantined",
] as const;

export type StatusKind = (typeof STATUS_KINDS)[number];

const STATUS_LABELS: Record<StatusKind, string> = {
  live: "Live",
  incubating: "Incubating",
  reserve: "Reserve",
  dead: "Dead",
  burned: "Burned",
  "kill-pending": "Kill pending",
  "eod-scheduled": "EOD scheduled",
  disconnected: "Disconnected",
  drift: "Drift",
  quarantined: "Quarantined",
};

const statusPillVariants = cva(
  "inline-flex items-center gap-1.5 rounded-sm font-medium whitespace-nowrap transition-colors",
  {
    variants: {
      kind: {
        // Filled — moss live, hearth-amber action-required, rust quarantined
        live: "bg-moss text-cream-light border-[1.5px] border-moss",
        "kill-pending": "bg-amber text-ink border-[1.5px] border-ink",
        quarantined: "bg-rust text-cream-light border-[1.5px] border-rust",
        // Outlined — everything else
        incubating: "bg-transparent text-ink border-[1.5px] border-sky",
        reserve: "bg-transparent text-ink border-[1.5px] border-sage",
        dead: "bg-transparent text-ink-soft border-[1.5px] border-ink-soft",
        burned: "bg-transparent text-rust border-[1.5px] border-rust",
        "eod-scheduled": "bg-transparent text-ink border-[1.5px] border-amber",
        disconnected: "bg-transparent text-ink-soft border-[1.5px] border-storm",
        drift: "bg-transparent text-ink border-[1.5px] border-honey",
      },
      size: {
        sm: "h-5 px-1.5 text-xs",
        md: "h-6 px-2 text-xs",
        lg: "h-7 px-2.5 text-sm",
      },
    },
    defaultVariants: {
      kind: "live",
      size: "md",
    },
  }
);

const DOT_COLORS: Record<StatusKind, string> = {
  live: "bg-cream-light",
  "kill-pending": "bg-ink",
  quarantined: "bg-cream-light",
  incubating: "bg-sky",
  reserve: "bg-sage",
  dead: "bg-ink-soft",
  burned: "bg-rust",
  "eod-scheduled": "bg-amber",
  disconnected: "bg-storm",
  drift: "bg-honey",
};

export interface StatusPillProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof statusPillVariants> {
  kind: StatusKind;
  label?: string;
  showDot?: boolean;
}

const StatusPill = React.forwardRef<HTMLSpanElement, StatusPillProps>(
  ({ className, kind, size, label, showDot = true, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(statusPillVariants({ kind, size }), className)}
        {...props}
      >
        {showDot && (
          <span
            className={cn("h-1.5 w-1.5 rounded-full shrink-0", DOT_COLORS[kind])}
            aria-hidden="true"
          />
        )}
        {label ?? STATUS_LABELS[kind]}
      </span>
    );
  }
);
StatusPill.displayName = "StatusPill";

export { StatusPill, statusPillVariants };
