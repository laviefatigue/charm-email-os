/**
 * VolumeBarChart — hand-rolled SVG stacked bar chart.
 *
 * Renders a daily-volume time-series with one or more stacked series per bar.
 * Designed so feeding it ESP-split data later (e.g. {entra: 8000, google: 4000})
 * requires no UI change — today's API only returns totals, and we use a single
 * `total` series. When daily_volume_snapshots gets per-ESP columns the chart
 * just stacks the new series automatically.
 *
 * Hover surfaces the date + per-series values + bar total. Lightweight: zero
 * external chart deps, sized via viewBox so it scales fluidly.
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface BarSeriesConfig {
  /** Key into each datum's `series` map. */
  key: string;
  /** Display label. */
  label: string;
  /** CSS color (use Village token CSS vars or hex). */
  color: string;
}

export interface VolumeBarDatum {
  /** ISO date string (YYYY-MM-DD or full ISO). */
  date: string;
  /** Map of series key → value. Sum is the bar total. */
  series: Record<string, number>;
}

/**
 * Horizontal constant line drawn across the plot — e.g. "package potential daily sends".
 * The bar y-scale expands to include the largest reference line value so the bar
 * isn't visually crushed when the target is well above current sending.
 */
export interface ReferenceLine {
  label: string;
  value: number;
  color: string;
  dashed?: boolean;
}

/**
 * Per-day overlay line that varies with the same x-axis as the bars — e.g.
 * "current daily capacity available." Length must equal data.length.
 */
export interface OverlayLine {
  label: string;
  color: string;
  /** One value per day, in the same order as data. */
  values: number[];
  dashed?: boolean;
}

export interface VolumeBarChartProps {
  data: VolumeBarDatum[];
  seriesConfig: BarSeriesConfig[];
  /** SVG height in px (width auto-scales via viewBox). */
  height?: number;
  /** Format function for tooltip + axis labels. */
  formatValue?: (n: number) => string;
  className?: string;
  /** Optional "no data" message override. */
  emptyMessage?: string;
  /** Optional horizontal reference lines (e.g. package potential). */
  referenceLines?: ReferenceLine[];
  /** Optional overlay lines varying per day (e.g. current capacity). */
  overlayLines?: OverlayLine[];
}

const DEFAULT_FMT = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
};

const CHART_WIDTH = 800;
const PADDING = { left: 48, right: 12, top: 16, bottom: 28 };

export function VolumeBarChart({
  data,
  seriesConfig,
  height = 220,
  formatValue = DEFAULT_FMT,
  className,
  emptyMessage = "No volume data yet.",
  referenceLines = [],
  overlayLines = [],
}: VolumeBarChartProps) {
  const [hover, setHover] = React.useState<{ idx: number; x: number; y: number } | null>(null);

  const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
  const plotHeight = height - PADDING.top - PADDING.bottom;

  const barTotals = React.useMemo(
    () =>
      data.map((d) =>
        seriesConfig.reduce((sum, s) => sum + (d.series[s.key] ?? 0), 0),
      ),
    [data, seriesConfig],
  );

  // y-axis includes the largest reference/overlay value so bars stay readable
  // when current sending is well below capacity or package target.
  const yMax = React.useMemo(() => {
    const refMax = referenceLines.reduce((m, r) => Math.max(m, r.value), 0);
    const overlayMax = overlayLines.reduce(
      (m, o) => Math.max(m, ...(o.values.length > 0 ? o.values : [0])),
      0,
    );
    const max = Math.max(...barTotals, refMax, overlayMax, 1);
    const scale = Math.pow(10, Math.floor(Math.log10(max)));
    return Math.ceil(max / scale) * scale;
  }, [barTotals, referenceLines, overlayLines]);

  const yLabels = [0, 0.25, 0.5, 0.75, 1].map((r) => Math.round(yMax * r));

  if (data.length === 0) {
    return (
      <div className={cn("flex items-center justify-center text-sm text-ink-soft py-12 border border-dashed border-border rounded-md", className)}>
        {emptyMessage}
      </div>
    );
  }

  const barSlotWidth = plotWidth / data.length;
  const barInnerPad = Math.max(1, barSlotWidth * 0.15);
  const barWidth = Math.max(2, barSlotWidth - barInnerPad);

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        className="w-full h-auto block"
        preserveAspectRatio="none"
        onMouseLeave={() => setHover(null)}
      >
        {/* Y-axis grid + labels */}
        {yLabels.map((label, i) => {
          const ratio = i / (yLabels.length - 1);
          const y = PADDING.top + plotHeight - ratio * plotHeight;
          return (
            <g key={i}>
              <line
                x1={PADDING.left}
                y1={y}
                x2={CHART_WIDTH - PADDING.right}
                y2={y}
                stroke="currentColor"
                strokeOpacity={i === 0 ? 0.4 : 0.12}
                strokeWidth={1}
                strokeDasharray={i === 0 ? "" : "3 3"}
              />
              <text
                x={PADDING.left - 6}
                y={y + 3}
                fontSize="10"
                textAnchor="end"
                fill="currentColor"
                fillOpacity={0.55}
                fontFamily="ui-monospace, monospace"
              >
                {formatValue(label)}
              </text>
            </g>
          );
        })}

        {/* Bars (stacked) */}
        {data.map((datum, i) => {
          const slotX = PADDING.left + i * barSlotWidth;
          const x = slotX + barInnerPad / 2;
          let stackY = PADDING.top + plotHeight;

          return (
            <g
              key={i}
              onMouseEnter={() =>
                setHover({ idx: i, x: slotX + barSlotWidth / 2, y: PADDING.top })
              }
            >
              {/* invisible hit area for full bar slot */}
              <rect
                x={slotX}
                y={PADDING.top}
                width={barSlotWidth}
                height={plotHeight}
                fill="transparent"
              />
              {seriesConfig.map((s) => {
                const value = datum.series[s.key] ?? 0;
                if (value <= 0) return null;
                const h = (value / yMax) * plotHeight;
                stackY -= h;
                return (
                  <rect
                    key={s.key}
                    x={x}
                    y={stackY}
                    width={barWidth}
                    height={h}
                    fill={s.color}
                    opacity={hover && hover.idx !== i ? 0.45 : 1}
                  >
                    <title>
                      {`${formatDateShort(datum.date)} · ${s.label}: ${formatValue(value)}`}
                    </title>
                  </rect>
                );
              })}
            </g>
          );
        })}

        {/* Overlay lines (e.g. current daily capacity, varies day-by-day) */}
        {overlayLines.map((line, lineIdx) => {
          if (line.values.length === 0) return null;
          const path = line.values
            .map((v, i) => {
              const x = PADDING.left + i * barSlotWidth + barSlotWidth / 2;
              const y = PADDING.top + plotHeight - (yMax > 0 ? (v / yMax) * plotHeight : 0);
              return `${i === 0 ? "M" : "L"} ${x} ${y}`;
            })
            .join(" ");
          return (
            <path
              key={`overlay-${lineIdx}`}
              d={path}
              fill="none"
              stroke={line.color}
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={line.dashed ? "4 4" : ""}
              opacity={0.85}
            />
          );
        })}

        {/* Reference lines (e.g. package potential, constant horizontal) */}
        {referenceLines.map((ref, refIdx) => {
          const y = PADDING.top + plotHeight - (yMax > 0 ? (ref.value / yMax) * plotHeight : 0);
          return (
            <g key={`ref-${refIdx}`}>
              <line
                x1={PADDING.left}
                y1={y}
                x2={CHART_WIDTH - PADDING.right}
                y2={y}
                stroke={ref.color}
                strokeWidth={1.5}
                strokeDasharray={ref.dashed === false ? "" : "5 4"}
                opacity={0.7}
              />
              <text
                x={CHART_WIDTH - PADDING.right - 4}
                y={y - 4}
                fontSize="10"
                fontWeight="500"
                textAnchor="end"
                fill={ref.color}
                fontFamily="ui-monospace, monospace"
              >
                {ref.label} · {formatValue(ref.value)}
              </text>
            </g>
          );
        })}

        {/* X-axis labels (every ~5th day) */}
        {data.map((d, i) => {
          const showEvery = Math.max(1, Math.ceil(data.length / 8));
          if (i % showEvery !== 0 && i !== data.length - 1) return null;
          const x = PADDING.left + i * barSlotWidth + barSlotWidth / 2;
          return (
            <text
              key={`xl-${i}`}
              x={x}
              y={height - 8}
              fontSize="10"
              textAnchor="middle"
              fill="currentColor"
              fillOpacity={0.55}
              fontFamily="ui-monospace, monospace"
            >
              {formatDateShort(d.date)}
            </text>
          );
        })}

        {/* Hover guideline */}
        {hover && (
          <line
            x1={hover.x}
            y1={PADDING.top}
            x2={hover.x}
            y2={PADDING.top + plotHeight}
            stroke="currentColor"
            strokeOpacity={0.25}
            strokeDasharray="2 2"
            strokeWidth={1}
          />
        )}
      </svg>

      {/* Tooltip */}
      {hover && data[hover.idx] && (
        <div
          className="absolute pointer-events-none rounded-md border-[1.5px] border-border-bold bg-card shadow-flat-sm px-3 py-2 text-xs"
          style={{
            left: `${(hover.x / CHART_WIDTH) * 100}%`,
            top: 4,
            transform: "translateX(-50%)",
          }}
        >
          <p className="font-medium mb-1">{formatDateLong(data[hover.idx].date)}</p>
          {seriesConfig.map((s) => {
            const v = data[hover.idx].series[s.key] ?? 0;
            if (v <= 0 && seriesConfig.length > 1) return null;
            return (
              <p key={s.key} className="flex items-center gap-1.5 font-mono">
                <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.color }} />
                <span className="text-ink-soft">{s.label}:</span>
                <span>{formatValue(v)}</span>
              </p>
            );
          })}
          {seriesConfig.length > 1 && barTotals[hover.idx] > 0 && (
            <p className="mt-1 pt-1 border-t border-border font-mono">
              Total: {formatValue(barTotals[hover.idx])}
            </p>
          )}
          {overlayLines.length > 0 && (
            <div className="mt-1 pt-1 border-t border-border space-y-0.5">
              {overlayLines.map((line) => (
                <p key={line.label} className="flex items-center gap-1.5 font-mono">
                  <span className="inline-block h-0.5 w-3" style={{ background: line.color }} />
                  <span className="text-ink-soft">{line.label}:</span>
                  <span>{formatValue(line.values[hover.idx] ?? 0)}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend — includes bars (when multi-series), overlay lines, reference lines */}
      {(seriesConfig.length > 1 || overlayLines.length > 0 || referenceLines.length > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
          {seriesConfig.length > 1 && seriesConfig.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
              <span className="text-ink-soft">{s.label}</span>
            </span>
          ))}
          {overlayLines.map((line) => (
            <span key={line.label} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4" style={{ background: line.color }} />
              <span className="text-ink-soft">{line.label}</span>
            </span>
          ))}
          {referenceLines.map((ref) => (
            <span key={ref.label} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-4"
                style={{
                  background: ref.color,
                  backgroundImage: ref.dashed === false ? undefined : `repeating-linear-gradient(to right, ${ref.color} 0 4px, transparent 4px 8px)`,
                }}
              />
              <span className="text-ink-soft">{ref.label}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatDateLong(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
