'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus, Zap, AlertCircle, Activity } from 'lucide-react';
import type { DailyVolumeSnapshot, KillEventAnnotation } from '@/lib/types/health';

interface SendingCapacityChartProps {
  snapshots: DailyVolumeSnapshot[];
  killEvents: KillEventAnnotation[];
  totalEmailsSent: number;
  avgDailyCapacity: number;
  avgUtilizationPct: number;
  totalKills: number;
  className?: string;
}

export function SendingCapacityChart({
  snapshots,
  killEvents,
  totalEmailsSent,
  avgDailyCapacity,
  avgUtilizationPct,
  totalKills,
  className,
}: SendingCapacityChartProps) {
  // Take last 30 days for display
  const chartData = useMemo(() => {
    return snapshots.slice(-30);
  }, [snapshots]);

  // Calculate max values for scaling
  const maxCapacity = useMemo(() => {
    return Math.max(...chartData.map(d => d.dailyCapacityAvailable), 1);
  }, [chartData]);

  const maxSent = useMemo(() => {
    return Math.max(...chartData.map(d => d.emailsSent), 1);
  }, [chartData]);

  // Use the larger of capacity or sent for Y-axis scale
  const yMax = Math.max(maxCapacity, maxSent);
  const yScale = Math.ceil(yMax / 100) * 100 || 100;

  // Calculate trend from last 7 days vs previous 7 days
  const trend = useMemo(() => {
    if (chartData.length < 14) return 'stable';
    const recent7 = chartData.slice(-7);
    const prev7 = chartData.slice(-14, -7);
    const recentAvg = recent7.reduce((sum, d) => sum + d.emailsSent, 0) / 7;
    const prevAvg = prev7.reduce((sum, d) => sum + d.emailsSent, 0) / 7;

    if (recentAvg > prevAvg * 1.1) return 'up';
    if (recentAvg < prevAvg * 0.9) return 'down';
    return 'stable';
  }, [chartData]);

  // Kill events indexed by date for quick lookup
  const killEventsByDate = useMemo(() => {
    const map = new Map<string, KillEventAnnotation>();
    for (const event of killEvents) {
      const dateStr = event.date.split('T')[0];
      map.set(dateStr, event);
    }
    return map;
  }, [killEvents]);

  // Chart dimensions
  const chartWidth = 600;
  const chartHeight = 180;
  const padding = { left: 45, right: 20, top: 20, bottom: 30 };
  const plotWidth = chartWidth - padding.left - padding.right;
  const plotHeight = chartHeight - padding.top - padding.bottom;

  // Build SVG path for area chart
  const buildAreaPath = (data: DailyVolumeSnapshot[], getValue: (d: DailyVolumeSnapshot) => number): { linePath: string; areaPath: string } => {
    if (data.length === 0) return { linePath: '', areaPath: '' };

    const xStep = plotWidth / (data.length - 1 || 1);

    let linePath = '';
    let areaPath = '';

    data.forEach((d, i) => {
      const x = padding.left + i * xStep;
      const value = getValue(d);
      const y = padding.top + plotHeight - (value / yScale) * plotHeight;

      if (i === 0) {
        linePath += `M ${x} ${y}`;
        areaPath += `M ${x} ${padding.top + plotHeight} L ${x} ${y}`;
      } else {
        linePath += ` L ${x} ${y}`;
        areaPath += ` L ${x} ${y}`;
      }
    });

    // Close area path
    const lastX = padding.left + (data.length - 1) * xStep;
    areaPath += ` L ${lastX} ${padding.top + plotHeight} Z`;

    return { linePath, areaPath };
  };

  const capacityPaths = buildAreaPath(chartData, d => d.dailyCapacityAvailable);
  const sentPaths = buildAreaPath(chartData, d => d.emailsSent);

  const trendConfig = {
    up: { icon: <TrendingUp className="w-3 h-3" />, color: 'text-green-600', label: 'Growing' },
    down: { icon: <TrendingDown className="w-3 h-3" />, color: 'text-amber-600', label: 'Declining' },
    stable: { icon: <Minus className="w-3 h-3" />, color: 'text-slate-500', label: 'Stable' },
  };

  const currentTrend = trendConfig[trend];

  // Y-axis labels
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map(ratio => Math.round(yScale * ratio));

  // Calculate summary stats
  const recentCapacity = chartData.length > 0 ? chartData[chartData.length - 1].dailyCapacityAvailable : 0;
  const recentSent = chartData.length > 0 ? chartData[chartData.length - 1].emailsSent : 0;

  // Generate insight message
  const insight = useMemo(() => {
    if (avgUtilizationPct < 20) {
      return {
        icon: <AlertCircle className="h-4 w-4 text-amber-500" />,
        message: 'Low utilization. Consider increasing campaign volume or reducing infrastructure.',
        severity: 'warning',
      };
    }
    if (avgUtilizationPct > 80) {
      return {
        icon: <Zap className="h-4 w-4 text-green-500" />,
        message: 'High utilization. Infrastructure is being used efficiently.',
        severity: 'info',
      };
    }
    if (totalKills > 10) {
      return {
        icon: <AlertCircle className="h-4 w-4 text-red-500" />,
        message: `${totalKills} inbox retirements in this period. Review kill triggers and list quality.`,
        severity: 'critical',
      };
    }
    return {
      icon: <Activity className="h-4 w-4 text-blue-500" />,
      message: 'Capacity and volume are balanced. Infrastructure is healthy.',
      severity: 'info',
    };
  }, [avgUtilizationPct, totalKills]);

  if (chartData.length === 0) {
    return (
      <Card className={cn('', className)}>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold">Sending Capacity Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            <div className="text-center">
              <Activity className="h-12 w-12 mx-auto mb-2 opacity-30" />
              <p>No volume data available yet</p>
              <p className="text-sm mt-1">Data will appear after the first daily snapshot</p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Sending Capacity Over Time</CardTitle>
          <Badge variant="outline" className={cn('gap-1', currentTrend.color)}>
            {currentTrend.icon}
            {currentTrend.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Stats */}
        <div className="flex items-center gap-6 text-sm flex-wrap">
          <div>
            <span className="text-muted-foreground">Current Capacity:</span>
            <span className="ml-2 font-semibold text-blue-600">{recentCapacity.toLocaleString()}/day</span>
          </div>
          <div className="border-l pl-6">
            <span className="text-muted-foreground">Utilization:</span>
            <span className={cn(
              'ml-2 font-semibold',
              avgUtilizationPct >= 70 ? 'text-green-600' :
              avgUtilizationPct >= 40 ? 'text-amber-600' : 'text-red-600'
            )}>
              {avgUtilizationPct.toFixed(1)}%
            </span>
          </div>
          <div className="border-l pl-6">
            <span className="text-muted-foreground">30-Day Volume:</span>
            <span className="ml-2 font-semibold">{totalEmailsSent.toLocaleString()}</span>
          </div>
          {totalKills > 0 && (
            <div className="border-l pl-6">
              <span className="text-muted-foreground">Retirements:</span>
              <span className="ml-2 font-semibold text-red-600">{totalKills}</span>
            </div>
          )}
        </div>

        {/* Area Chart */}
        <div className="relative">
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            className="w-full h-auto"
            style={{ maxHeight: '220px' }}
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Y-axis grid lines and labels */}
            {yLabels.map((label, i) => {
              const ratio = i / (yLabels.length - 1);
              const y = padding.top + plotHeight - ratio * plotHeight;
              return (
                <g key={i}>
                  <line
                    x1={padding.left}
                    y1={y}
                    x2={chartWidth - padding.right}
                    y2={y}
                    stroke="#e5e7eb"
                    strokeWidth="1"
                    strokeDasharray={i === 0 ? '0' : '4'}
                  />
                  <text
                    x={padding.left - 5}
                    y={y + 4}
                    fontSize="10"
                    fill="#9ca3af"
                    textAnchor="end"
                  >
                    {label >= 1000 ? `${(label / 1000).toFixed(0)}k` : label}
                  </text>
                </g>
              );
            })}

            {/* Capacity area (blue, behind) */}
            <path
              d={capacityPaths.areaPath}
              fill="rgba(59, 130, 246, 0.15)"
            />
            <path
              d={capacityPaths.linePath}
              fill="none"
              stroke="rgb(59, 130, 246)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Sent area (green, in front) */}
            <path
              d={sentPaths.areaPath}
              fill="rgba(34, 197, 94, 0.2)"
            />
            <path
              d={sentPaths.linePath}
              fill="none"
              stroke="rgb(34, 197, 94)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Kill event markers */}
            {chartData.map((d, i) => {
              const dateStr = d.date.split('T')[0];
              const killEvent = killEventsByDate.get(dateStr);
              if (!killEvent || killEvent.inboxesKilled === 0) return null;

              const xStep = plotWidth / (chartData.length - 1 || 1);
              const x = padding.left + i * xStep;

              return (
                <g key={`kill-${i}`}>
                  {/* Vertical line */}
                  <line
                    x1={x}
                    y1={padding.top}
                    x2={x}
                    y2={padding.top + plotHeight}
                    stroke="rgb(239, 68, 68)"
                    strokeWidth="1"
                    strokeDasharray="3"
                    opacity="0.6"
                  />
                  {/* Marker dot at top */}
                  <circle
                    cx={x}
                    cy={padding.top + 5}
                    r="4"
                    fill="rgb(239, 68, 68)"
                  />
                  {/* Kill count label */}
                  <text
                    x={x}
                    y={padding.top - 3}
                    fontSize="9"
                    fontWeight="600"
                    fill="rgb(239, 68, 68)"
                    textAnchor="middle"
                  >
                    -{killEvent.inboxesKilled}
                  </text>
                </g>
              );
            })}

            {/* X-axis labels (show every 5th day) */}
            {chartData.map((d, i) => {
              if (i % 5 !== 0 && i !== chartData.length - 1) return null;
              const xStep = plotWidth / (chartData.length - 1 || 1);
              const x = padding.left + i * xStep;
              const date = new Date(d.date);
              const label = `${date.getMonth() + 1}/${date.getDate()}`;

              return (
                <text
                  key={`label-${i}`}
                  x={x}
                  y={chartHeight - 5}
                  fontSize="10"
                  fill="#6b7280"
                  textAnchor="middle"
                >
                  {label}
                </text>
              );
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-blue-500" />
            <span className="text-muted-foreground">Daily Capacity</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-green-500" />
            <span className="text-muted-foreground">Emails Sent</span>
          </div>
          {totalKills > 0 && (
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded bg-red-500" />
              <span className="text-muted-foreground">Inbox Retirements</span>
            </div>
          )}
        </div>

        {/* Insight */}
        <div className={cn(
          'text-xs rounded-lg p-3 flex items-start gap-2',
          insight.severity === 'critical' ? 'bg-red-50 text-red-700' :
          insight.severity === 'warning' ? 'bg-amber-50 text-amber-700' :
          'bg-muted/50 text-muted-foreground'
        )}>
          {insight.icon}
          <span>{insight.message}</span>
        </div>
      </CardContent>
    </Card>
  );
}
