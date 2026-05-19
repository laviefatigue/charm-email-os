/**
 * DateRangePicker — preset buttons + custom range popover for AE trend monitoring.
 *
 * Presets: 7d / 14d / 30d / 90d / 180d. Custom opens a popover with two
 * native date inputs so an AE can pin to a specific incident window.
 *
 * Emits a {days: number, customStart?: Date, customEnd?: Date} state via
 * onChange — pages decide how to pass it through to API calls. Most charts
 * take days; for custom, derive days from (end - start).
 */
"use client";

import * as React from "react";
import { Calendar, ChevronDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface DateRangeValue {
  /** Number of days from today (always set, even for custom — derived for backend calls). */
  days: number;
  /** When set, indicates a pinned custom range. */
  customStart?: string; // YYYY-MM-DD
  customEnd?: string;   // YYYY-MM-DD
}

interface Preset {
  label: string;
  days: number;
}

const PRESETS: Preset[] = [
  { label: "7d", days: 7 },
  { label: "14d", days: 14 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "180d", days: 180 },
];

export interface DateRangePickerProps {
  value: DateRangeValue;
  onChange: (v: DateRangeValue) => void;
  className?: string;
}

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  const [customOpen, setCustomOpen] = React.useState(false);
  const [draftStart, setDraftStart] = React.useState(value.customStart ?? "");
  const [draftEnd, setDraftEnd] = React.useState(value.customEnd ?? "");

  const isCustomActive = !!(value.customStart && value.customEnd);

  const applyCustom = () => {
    if (!draftStart || !draftEnd) return;
    const start = new Date(draftStart);
    const end = new Date(draftEnd);
    if (isNaN(start.getTime()) || isNaN(end.getTime()) || end < start) return;
    const days = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1);
    onChange({ days, customStart: draftStart, customEnd: draftEnd });
    setCustomOpen(false);
  };

  return (
    <div className={cn("inline-flex items-center gap-1 rounded-md border-[1.5px] border-border bg-card p-0.5", className)}>
      {PRESETS.map((p) => {
        const active = !isCustomActive && value.days === p.days;
        return (
          <button
            key={p.label}
            type="button"
            onClick={() => onChange({ days: p.days })}
            className={cn(
              "h-7 px-2.5 rounded-sm text-xs font-medium transition-colors",
              active
                ? "bg-amber text-ink border border-ink"
                : "text-ink-soft hover:text-foreground hover:bg-muted"
            )}
          >
            {p.label}
          </button>
        );
      })}

      <Popover open={customOpen} onOpenChange={setCustomOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex items-center gap-1 h-7 px-2.5 rounded-sm text-xs font-medium transition-colors",
              isCustomActive
                ? "bg-amber text-ink border border-ink"
                : "text-ink-soft hover:text-foreground hover:bg-muted"
            )}
            aria-label="Custom date range"
          >
            <Calendar className="h-3 w-3" aria-hidden="true" />
            {isCustomActive ? `${value.customStart} → ${value.customEnd}` : "Custom"}
            <ChevronDown className="h-3 w-3" aria-hidden="true" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" sideOffset={6} className="w-72 p-3 space-y-2.5">
          <p className="text-xs font-medium text-ink-soft uppercase tracking-wider">
            Custom range
          </p>
          <div className="space-y-2">
            <label className="block">
              <span className="text-xs text-ink-soft">Start</span>
              <input
                type="date"
                value={draftStart}
                onChange={(e) => setDraftStart(e.target.value)}
                className="mt-1 w-full h-8 px-2 rounded-sm border-[1.5px] border-border bg-background text-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs text-ink-soft">End</span>
              <input
                type="date"
                value={draftEnd}
                onChange={(e) => setDraftEnd(e.target.value)}
                className="mt-1 w-full h-8 px-2 rounded-sm border-[1.5px] border-border bg-background text-sm"
              />
            </label>
          </div>
          <div className="flex items-center justify-end gap-1.5 pt-1">
            {isCustomActive && (
              <button
                type="button"
                onClick={() => {
                  onChange({ days: 30 });
                  setDraftStart("");
                  setDraftEnd("");
                  setCustomOpen(false);
                }}
                className="h-7 px-2.5 rounded-sm text-xs text-ink-soft hover:text-foreground"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={applyCustom}
              disabled={!draftStart || !draftEnd}
              className={cn(
                "h-7 px-3 rounded-sm text-xs font-medium border-[1.5px]",
                draftStart && draftEnd
                  ? "bg-amber text-ink border-ink"
                  : "border-border text-ink-soft cursor-not-allowed opacity-60"
              )}
            >
              Apply
            </button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
