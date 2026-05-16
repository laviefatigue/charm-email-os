/**
 * Per-agent monthly LLM cost budget meter.
 * 0-80% moss · 80-100% honey · >100% rust.
 * Reflects agents.spent_monthly_cents vs agents.budget_monthly_cents per [[../architecture/agent-runtime]] §Cost Tracking.
 * Tokens: --moss, --honey, --rust, --cream, --ink-soft
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface CostBudgetMeterProps extends React.HTMLAttributes<HTMLDivElement> {
  spentCents: number;
  budgetCents: number;
  size?: "sm" | "md" | "lg";
  showLabels?: boolean;
  period?: "month" | "year";
}

function formatUsd(cents: number): string {
  const dollars = cents / 100;
  if (dollars < 10) return `$${dollars.toFixed(2)}`;
  if (dollars < 1000) return `$${dollars.toFixed(0)}`;
  return `$${(dollars / 1000).toFixed(1)}k`;
}

const SIZE_CLASSES = {
  sm: { bar: "h-1", label: "text-xs", gap: "gap-1" },
  md: { bar: "h-2", label: "text-sm", gap: "gap-1.5" },
  lg: { bar: "h-3", label: "text-base", gap: "gap-2" },
} as const;

const CostBudgetMeter = React.forwardRef<HTMLDivElement, CostBudgetMeterProps>(
  (
    {
      className,
      spentCents,
      budgetCents,
      size = "md",
      showLabels = true,
      period = "month",
      ...props
    },
    ref
  ) => {
    const utilization = budgetCents > 0 ? spentCents / budgetCents : 0;
    const pct = Math.min(100, Math.round(utilization * 100));
    const overage = utilization > 1;

    const fillTone =
      utilization > 1
        ? "bg-rust"
        : utilization > 0.8
          ? "bg-honey"
          : "bg-moss";

    const statusLabel =
      utilization > 1
        ? `Over budget • +${Math.round((utilization - 1) * 100)}%`
        : utilization > 0.8
          ? "Approaching cap"
          : "Healthy";

    const statusToneClass =
      utilization > 1
        ? "text-rust"
        : utilization > 0.8
          ? "text-honey"
          : "text-moss";

    const sizes = SIZE_CLASSES[size];

    return (
      <div
        ref={ref}
        className={cn("flex flex-col w-full", sizes.gap, className)}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Budget: ${formatUsd(spentCents)} of ${formatUsd(budgetCents)} this ${period}`}
        {...props}
      >
        {showLabels && (
          <div className={cn("flex justify-between items-baseline font-mono", sizes.label)}>
            <span className="text-ink">
              {formatUsd(spentCents)}{" "}
              <span className="text-ink-soft">/ {formatUsd(budgetCents)}</span>
            </span>
            <span className={cn("text-xs font-medium", statusToneClass)}>
              {pct}%
            </span>
          </div>
        )}

        <div
          className={cn(
            "w-full rounded-full bg-cream border-[1.5px] border-ink overflow-hidden",
            sizes.bar
          )}
        >
          <div
            className={cn("h-full transition-all duration-300 ease-out", fillTone)}
            style={{ width: `${pct}%` }}
          />
        </div>

        {showLabels && (
          <div className={cn("flex justify-between items-center text-xs", overage ? "text-rust" : "text-ink-soft")}>
            <span>{statusLabel}</span>
            <span className="capitalize">{period}</span>
          </div>
        )}
      </div>
    );
  }
);
CostBudgetMeter.displayName = "CostBudgetMeter";

export { CostBudgetMeter };
