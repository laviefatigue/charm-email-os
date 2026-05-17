/**
 * GanttStrip — lightweight CSS-based timeline renderer.
 * Bars positioned by start_at → (start_at + estimated_hours) or due_at.
 * Today line in amber. Click bar → onItemClick(itemId).
 *
 * Village-styled: warm ink outlines, no dependencies, Village shadows on hover.
 * Tokens: --amber, --moss, --honey, --rust, --sky, --copper, --ink, --ink-soft
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { addDays, differenceInDays, format, startOfDay } from "date-fns";
import { cn } from "@/lib/utils";

export interface GanttItem {
  id: string;
  label: string;
  start: Date;
  end: Date;
  href?: string;
  /** Lane label (e.g. project name or assignee) for grouping rows. */
  lane?: string;
  /** Tint key — pick from Village palette tokens. */
  tone?: "amber" | "moss" | "honey" | "rust" | "sky" | "copper" | "sage" | "rose";
  /** Subtitle under the bar — e.g. assignee, status. */
  subtitle?: string;
  /** Percent complete 0-100 for progress shading inside the bar. */
  percentDone?: number;
}

export interface GanttStripProps {
  items: GanttItem[];
  /** Display window. If omitted: 14 days starting today. */
  startDate?: Date;
  daysVisible?: number;
  /** Compact = thinner rows (for mini Gantt inside project card). */
  compact?: boolean;
  className?: string;
  /** Empty-state message when no items. */
  emptyMessage?: string;
}

const TONE_BG: Record<NonNullable<GanttItem["tone"]>, string> = {
  amber: "bg-amber",
  moss: "bg-moss",
  honey: "bg-honey",
  rust: "bg-rust",
  sky: "bg-sky",
  copper: "bg-copper",
  sage: "bg-sage",
  rose: "bg-rose",
};

const TONE_FG: Record<NonNullable<GanttItem["tone"]>, string> = {
  amber: "text-ink",
  moss: "text-cream-light",
  honey: "text-ink",
  rust: "text-cream-light",
  sky: "text-ink",
  copper: "text-cream-light",
  sage: "text-ink",
  rose: "text-ink",
};

const DAY_PX_DEFAULT = 56; // tunable bar-day width
const DAY_PX_COMPACT = 32;

export function GanttStrip({
  items,
  startDate,
  daysVisible = 14,
  compact = false,
  className,
  emptyMessage = "No scheduled work in this window",
}: GanttStripProps) {
  const start = React.useMemo(
    () => startOfDay(startDate ?? new Date()),
    [startDate]
  );
  const dayPx = compact ? DAY_PX_COMPACT : DAY_PX_DEFAULT;
  const rowHeight = compact ? 28 : 40;
  const totalWidth = daysVisible * dayPx;

  // Build day axis
  const days = React.useMemo(
    () => Array.from({ length: daysVisible }, (_, i) => addDays(start, i)),
    [start, daysVisible]
  );

  // Group items by lane
  const lanes = React.useMemo(() => {
    const map = new Map<string, GanttItem[]>();
    for (const it of items) {
      const key = it.lane ?? "—";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(it);
    }
    return Array.from(map.entries());
  }, [items]);

  if (items.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center text-sm text-ink-soft py-10 px-6",
          "border border-dashed border-border rounded-md",
          className
        )}
      >
        {emptyMessage}
      </div>
    );
  }

  const todayOffsetDays = differenceInDays(startOfDay(new Date()), start);
  const todayInWindow = todayOffsetDays >= 0 && todayOffsetDays < daysVisible;

  return (
    <div className={cn("rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden", className)}>
      <div className="relative overflow-x-auto custom-scrollbar">
        {/* Day axis header */}
        <header
          className="flex sticky top-0 z-10 bg-muted/40 border-b border-border"
          style={{ minWidth: totalWidth + 160 }}
        >
          <div className="shrink-0 w-40 px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-ink-soft border-r border-border">
            Lane
          </div>
          <div className="flex relative" style={{ width: totalWidth }}>
            {days.map((d, i) => (
              <div
                key={i}
                className={cn(
                  "shrink-0 flex flex-col items-center justify-center py-1 text-xs border-r border-border last:border-r-0",
                  d.getDay() === 0 || d.getDay() === 6 ? "bg-cream/40" : ""
                )}
                style={{ width: dayPx }}
                title={format(d, "yyyy-MM-dd")}
              >
                <span className="font-mono text-[10px] text-ink-soft uppercase">
                  {format(d, "EEE")}
                </span>
                <span className="font-mono font-medium">{format(d, "d")}</span>
              </div>
            ))}
            {todayInWindow && (
              <div
                className="absolute top-0 bottom-0 w-px bg-amber pointer-events-none z-20"
                style={{ left: todayOffsetDays * dayPx + dayPx / 2 }}
                aria-label="today"
              />
            )}
          </div>
        </header>

        {/* Lanes */}
        {lanes.map(([laneName, laneItems]) => (
          <div
            key={laneName}
            className="flex border-b border-border last:border-b-0"
            style={{ minWidth: totalWidth + 160 }}
          >
            <div className="shrink-0 w-40 px-3 py-2 text-xs font-medium border-r border-border bg-muted/20 flex items-center min-h-[40px]">
              <span className="truncate" title={laneName}>{laneName}</span>
            </div>
            <div
              className="flex-1 relative"
              style={{ width: totalWidth, minHeight: rowHeight + 8 }}
            >
              {/* Grid lines for days */}
              {days.map((_, i) => (
                <div
                  key={i}
                  className="absolute top-0 bottom-0 border-r border-border/50 last:border-r-0"
                  style={{ left: i * dayPx, width: dayPx }}
                />
              ))}
              {todayInWindow && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-amber pointer-events-none z-20"
                  style={{ left: todayOffsetDays * dayPx + dayPx / 2 }}
                />
              )}
              {/* Bars */}
              {laneItems.map((it, idx) => {
                const startOffset = differenceInDays(startOfDay(it.start), start);
                const lengthDays = Math.max(0.25, differenceInDays(startOfDay(it.end), startOfDay(it.start)) + 1);
                // Clamp to window
                const clampedStart = Math.max(0, startOffset);
                const clampedEnd = Math.min(daysVisible, startOffset + lengthDays);
                const visibleLength = clampedEnd - clampedStart;
                if (visibleLength <= 0) return null;
                const tone = it.tone ?? "sage";
                const bar = (
                  <div
                    className={cn(
                      "absolute rounded-md flex flex-col justify-center px-2 overflow-hidden",
                      "border-[1.5px] border-ink shadow-flat-sm transition-shadow",
                      TONE_BG[tone],
                      TONE_FG[tone],
                      it.href && "cursor-pointer hover:shadow-flat"
                    )}
                    style={{
                      left: clampedStart * dayPx + 2,
                      width: visibleLength * dayPx - 4,
                      top: 4 + idx * (rowHeight + 4),
                      height: rowHeight,
                    }}
                    title={`${it.label} · ${format(it.start, "MMM d")} → ${format(it.end, "MMM d")}`}
                  >
                    <span className="text-xs font-medium truncate leading-tight">
                      {it.label}
                    </span>
                    {!compact && it.subtitle && (
                      <span className="text-[10px] truncate opacity-80 leading-tight">
                        {it.subtitle}
                      </span>
                    )}
                    {typeof it.percentDone === "number" && it.percentDone > 0 && (
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-ink/15 pointer-events-none"
                        style={{ width: `${Math.min(100, it.percentDone)}%` }}
                      />
                    )}
                  </div>
                );
                if (it.href) {
                  return (
                    <Link
                      key={it.id}
                      href={it.href}
                      className="absolute"
                      style={{ left: 0, top: 0, right: 0, bottom: 0, pointerEvents: "none" }}
                    >
                      <span style={{ pointerEvents: "auto" }}>{bar}</span>
                    </Link>
                  );
                }
                return <React.Fragment key={it.id}>{bar}</React.Fragment>;
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
