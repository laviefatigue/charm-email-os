/**
 * TrendLineChart — hand-rolled SVG multi-line chart for daily trend visualization.
 *
 * Same data shape as VolumeBarChart so they can share a backing series. Each
 * series renders as its own line; values can have wildly different scales
 * (counts vs percentages) via the `secondaryScale` config — secondary series
 * map to a right-side y-axis so a "kills per day" line can sit on the same
 * chart as a "live inboxes" line without being crushed to zero.
 *
 * Hover shows the date + every series value at that day. Designed for AE-focused
 * trend reading: visible grid, sparse x-labels, generous hover surface.
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface LineSeriesConfig {
  key: string;
  label: string;
  color: string;
  /** When true, this series uses the right-side y-axis. */
  secondaryScale?: boolean;
  /** Optional: line style. Default solid. */
  dashed?: boolean;
}

export interface TrendDatum {
  date: string;
  series: Record<string, number>;
}

export interface TrendLineChartProps {
  data: TrendDatum[];
  seriesConfig: LineSeriesConfig[];
  height?: number;
  /** Format function for left y-axis + tooltip primary values. */
  formatPrimary?: (n: number) => string;
  /** Format function for right y-axis values (when secondaryScale used). */
  formatSecondary?: (n: number) => string;
  className?: string;
  emptyMessage?: string;
}

const DEFAULT_FMT = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
};

const CHART_WIDTH = 800;
const PAD_LEFT = 48;
const PAD_RIGHT_BASE = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

export function TrendLineChart({
  data,
  seriesConfig,
  height = 200,
  formatPrimary = DEFAULT_FMT,
  formatSecondary = DEFAULT_FMT,
  className,
  emptyMessage = "No trend data yet.",
}: TrendLineChartProps) {
  const [hoverIdx, setHoverIdx] = React.useState<number | null>(null);

  const hasSecondary = seriesConfig.some((s) => s.secondaryScale);
  const padRight = hasSecondary ? 48 : PAD_RIGHT_BASE;
  const plotWidth = CHART_WIDTH - PAD_LEFT - padRight;
  const plotHeight = height - PAD_TOP - PAD_BOTTOM;

  const { primaryMax, secondaryMax } = React.useMemo(() => {
    let primary = 0;
    let secondary = 0;
    for (const datum of data) {
      for (const s of seriesConfig) {
        const v = datum.series[s.key] ?? 0;
        if (s.secondaryScale) {
          if (v > secondary) secondary = v;
        } else {
          if (v > primary) primary = v;
        }
      }
    }
    return {
      primaryMax: niceCeil(primary),
      secondaryMax: niceCeil(secondary),
    };
  }, [data, seriesConfig]);

  if (data.length === 0) {
    return (
      <div className={cn("flex items-center justify-center text-sm text-ink-soft py-12 border border-dashed border-border rounded-md", className)}>
        {emptyMessage}
      </div>
    );
  }

  const xStep = data.length > 1 ? plotWidth / (data.length - 1) : 0;
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map((r) => r);

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        className="w-full h-auto block"
        preserveAspectRatio="none"
        onMouseLeave={() => setHoverIdx(null)}
        onMouseMove={(e) => {
          const target = e.currentTarget;
          const rect = target.getBoundingClientRect();
          const xPx = e.clientX - rect.left;
          const xRatio = xPx / rect.width;
          const xSvg = xRatio * CHART_WIDTH;
          const inPlot = xSvg - PAD_LEFT;
          if (inPlot < 0 || inPlot > plotWidth) {
            setHoverIdx(null);
            return;
          }
          const idx = Math.round(inPlot / Math.max(xStep, 1));
          if (idx >= 0 && idx < data.length) setHoverIdx(idx);
        }}
      >
        {/* Y-axis grid + primary labels */}
        {yLabels.map((r, i) => {
          const y = PAD_TOP + plotHeight - r * plotHeight;
          return (
            <g key={i}>
              <line
                x1={PAD_LEFT}
                y1={y}
                x2={CHART_WIDTH - padRight}
                y2={y}
                stroke="currentColor"
                strokeOpacity={r === 0 ? 0.4 : 0.12}
                strokeWidth={1}
                strokeDasharray={r === 0 ? "" : "3 3"}
              />
              <text
                x={PAD_LEFT - 6}
                y={y + 3}
                fontSize="10"
                textAnchor="end"
                fill="currentColor"
                fillOpacity={0.55}
                fontFamily="ui-monospace, monospace"
              >
                {formatPrimary(primaryMax * r)}
              </text>
              {hasSecondary && (
                <text
                  x={CHART_WIDTH - padRight + 6}
                  y={y + 3}
                  fontSize="10"
                  textAnchor="start"
                  fill="currentColor"
                  fillOpacity={0.45}
                  fontFamily="ui-monospace, monospace"
                >
                  {formatSecondary(secondaryMax * r)}
                </text>
              )}
            </g>
          );
        })}

        {/* Lines */}
        {seriesConfig.map((s) => {
          const scaleMax = s.secondaryScale ? secondaryMax : primaryMax;
          const path = data
            .map((d, i) => {
              const x = PAD_LEFT + i * xStep;
              const v = d.series[s.key] ?? 0;
              const y = PAD_TOP + plotHeight - (scaleMax > 0 ? (v / scaleMax) * plotHeight : 0);
              return `${i === 0 ? "M" : "L"} ${x} ${y}`;
            })
            .join(" ");
          return (
            <path
              key={s.key}
              d={path}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={s.dashed ? "4 4" : ""}
            />
          );
        })}

        {/* Hover marker */}
        {hoverIdx !== null && (
          <>
            <line
              x1={PAD_LEFT + hoverIdx * xStep}
              y1={PAD_TOP}
              x2={PAD_LEFT + hoverIdx * xStep}
              y2={PAD_TOP + plotHeight}
              stroke="currentColor"
              strokeOpacity={0.3}
              strokeDasharray="2 2"
              strokeWidth={1}
            />
            {seriesConfig.map((s) => {
              const scaleMax = s.secondaryScale ? secondaryMax : primaryMax;
              const v = data[hoverIdx].series[s.key] ?? 0;
              if (scaleMax === 0) return null;
              const y = PAD_TOP + plotHeight - (v / scaleMax) * plotHeight;
              return (
                <circle
                  key={s.key}
                  cx={PAD_LEFT + hoverIdx * xStep}
                  cy={y}
                  r={3.5}
                  fill={s.color}
                  stroke="white"
                  strokeWidth={1.5}
                />
              );
            })}
          </>
        )}

        {/* X-axis labels */}
        {data.map((d, i) => {
          const showEvery = Math.max(1, Math.ceil(data.length / 8));
          if (i % showEvery !== 0 && i !== data.length - 1) return null;
          const x = PAD_LEFT + i * xStep;
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
      </svg>

      {/* Tooltip */}
      {hoverIdx !== null && data[hoverIdx] && (
        <div
          className="absolute pointer-events-none rounded-md border-[1.5px] border-border-bold bg-card shadow-flat-sm px-3 py-2 text-xs"
          style={{
            left: `${((PAD_LEFT + hoverIdx * xStep) / CHART_WIDTH) * 100}%`,
            top: 4,
            transform: "translateX(-50%)",
          }}
        >
          <p className="font-medium mb-1">{formatDateLong(data[hoverIdx].date)}</p>
          {seriesConfig.map((s) => {
            const v = data[hoverIdx].series[s.key] ?? 0;
            const fmt = s.secondaryScale ? formatSecondary : formatPrimary;
            return (
              <p key={s.key} className="flex items-center gap-1.5 font-mono">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
                <span className="text-ink-soft">{s.label}:</span>
                <span>{fmt(v)}</span>
              </p>
            );
          })}
        </div>
      )}

      {/* Legend */}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        {seriesConfig.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-ink-soft">
              {s.label}
              {s.secondaryScale && <span className="opacity-60"> (right axis)</span>}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function niceCeil(n: number): number {
  if (n <= 0) return 1;
  const scale = Math.pow(10, Math.floor(Math.log10(n)));
  return Math.ceil(n / scale) * scale;
}

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatDateLong(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
