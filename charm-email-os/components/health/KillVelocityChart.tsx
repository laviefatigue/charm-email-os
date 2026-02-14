'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';

interface WeeklyData {
  week: string;
  deaths: number;
  warnings?: number;  // NEW: Count of inboxes at warning/watching level
}

interface KillVelocityChartProps {
  weeklyData: WeeklyData[];
  currentWarnings?: number;  // NEW: Current inboxes at risk
  className?: string;
}

export function KillVelocityChart({ weeklyData, currentWarnings = 0, className }: KillVelocityChartProps) {
  // Ensure we have 5 weeks of data, padding with zeros if needed
  const chartData = useMemo(() => {
    const data = [...weeklyData].slice(-5);
    while (data.length < 5) {
      data.unshift({ week: '', deaths: 0, warnings: 0 });
    }
    return data;
  }, [weeklyData]);

  // Calculate max for scaling (consider both deaths and warnings)
  const maxValue = useMemo(() => {
    const maxDeaths = Math.max(...chartData.map(d => d.deaths), 1);
    const maxWarnings = Math.max(...chartData.map(d => d.warnings || 0), 0);
    return Math.ceil(Math.max(maxDeaths, maxWarnings) / 5) * 5; // Round up to nearest 5
  }, [chartData]);

  // Calculate trend
  const trend = useMemo(() => {
    if (chartData.length < 2) return 'stable';
    const recent = chartData.slice(-2);
    if (recent[1].deaths > recent[0].deaths) return 'up';
    if (recent[1].deaths < recent[0].deaths) return 'down';
    return 'stable';
  }, [chartData]);

  // Total deaths in current week vs previous
  const currentWeekDeaths = chartData[chartData.length - 1]?.deaths || 0;
  const totalDeaths = chartData.reduce((sum, d) => sum + d.deaths, 0);

  // Check if warnings data is available
  const hasWarningsData = chartData.some(d => (d.warnings || 0) > 0) || currentWarnings > 0;

  const trendConfig = {
    up: { icon: <TrendingUp className="w-3 h-3" />, color: 'text-red-600', label: 'Increasing' },
    down: { icon: <TrendingDown className="w-3 h-3" />, color: 'text-green-600', label: 'Decreasing' },
    stable: { icon: <Minus className="w-3 h-3" />, color: 'text-slate-500', label: 'Stable' },
  };

  const currentTrend = trendConfig[trend];

  // Chart dimensions
  const chartHeight = 120;
  const chartWidth = 300;
  const barWidth = 40;
  const barGap = 20;

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Kill Velocity</CardTitle>
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
            <span className="text-muted-foreground">This Week:</span>
            <span className="ml-2 font-semibold text-red-600">{currentWeekDeaths} deaths</span>
          </div>
          <div className="border-l pl-6">
            <span className="text-muted-foreground">5-Week Total:</span>
            <span className="ml-2 font-semibold">{totalDeaths} deaths</span>
          </div>
          {currentWarnings > 0 && (
            <div className="border-l pl-6">
              <span className="text-muted-foreground flex items-center gap-1">
                <AlertTriangle className="h-3 w-3 text-amber-500" />
                At Risk:
              </span>
              <span className="ml-2 font-semibold text-amber-600">{currentWarnings} inboxes</span>
            </div>
          )}
        </div>

        {/* Bar Chart */}
        <div className="relative">
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight + 30}`}
            className="w-full h-auto"
            style={{ maxHeight: '180px' }}
          >
            {/* Y-axis grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => (
              <g key={i}>
                <line
                  x1="0"
                  y1={chartHeight - (ratio * chartHeight)}
                  x2={chartWidth}
                  y2={chartHeight - (ratio * chartHeight)}
                  stroke="#e5e7eb"
                  strokeWidth="1"
                  strokeDasharray={i === 0 ? "0" : "4"}
                />
                <text
                  x="-5"
                  y={chartHeight - (ratio * chartHeight) + 4}
                  fontSize="10"
                  fill="#9ca3af"
                  textAnchor="end"
                >
                  {Math.round(maxValue * ratio)}
                </text>
              </g>
            ))}

            {/* Bars */}
            {chartData.map((d, i) => {
              const barHeight = (d.deaths / maxValue) * chartHeight;
              const x = i * (barWidth + barGap) + 30;
              const y = chartHeight - barHeight;

              // Warning dot position (if warnings data available)
              const warningCount = d.warnings || 0;
              const warningY = warningCount > 0
                ? chartHeight - (warningCount / maxValue) * chartHeight
                : 0;

              return (
                <g key={i}>
                  {/* Death Bar */}
                  <rect
                    x={x}
                    y={y}
                    width={barWidth}
                    height={Math.max(barHeight, 2)}
                    rx="4"
                    fill={i === chartData.length - 1 ? '#ef4444' : '#fca5a5'}
                    className="transition-all hover:opacity-80"
                  />
                  {/* Warning marker (amber dot above bar) */}
                  {hasWarningsData && warningCount > 0 && (
                    <>
                      <circle
                        cx={x + barWidth / 2}
                        cy={warningY}
                        r="5"
                        fill="#f59e0b"
                        stroke="white"
                        strokeWidth="1.5"
                      />
                      <text
                        x={x + barWidth / 2}
                        y={warningY - 8}
                        fontSize="9"
                        fontWeight="500"
                        fill="#d97706"
                        textAnchor="middle"
                      >
                        {warningCount}
                      </text>
                    </>
                  )}
                  {/* Death value on top of bar */}
                  {d.deaths > 0 && (
                    <text
                      x={x + barWidth / 2}
                      y={y - 5}
                      fontSize="11"
                      fontWeight="600"
                      fill="#374151"
                      textAnchor="middle"
                    >
                      {d.deaths}
                    </text>
                  )}
                  {/* Week label */}
                  <text
                    x={x + barWidth / 2}
                    y={chartHeight + 15}
                    fontSize="10"
                    fill="#6b7280"
                    textAnchor="middle"
                  >
                    {i === chartData.length - 1 ? 'Now' : `W${i + 1}`}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-red-400" />
            <span className="text-muted-foreground">Deaths</span>
          </div>
          {hasWarningsData && (
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-amber-500" />
              <span className="text-muted-foreground">At Risk (warnings)</span>
            </div>
          )}
        </div>

        {/* Insight */}
        <div className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3">
          {currentWarnings > 10 && (
            <span className="text-amber-600 font-medium block mb-1">
              {currentWarnings} inboxes currently approaching kill thresholds.
            </span>
          )}
          {trend === 'up' && currentWeekDeaths > 5 && (
            <span className="text-red-600 font-medium">
              High death rate detected. Review kill triggers and list quality.
            </span>
          )}
          {trend === 'down' && (
            <span className="text-green-600 font-medium">
              Death rate improving. Infrastructure health is stabilizing.
            </span>
          )}
          {trend === 'stable' && currentWeekDeaths <= 5 && !currentWarnings && (
            <span>
              Stable death rate within acceptable range.
            </span>
          )}
          {trend === 'stable' && currentWeekDeaths <= 5 && currentWarnings > 0 && currentWarnings <= 10 && (
            <span className="text-amber-600 font-medium">
              Low death rate but {currentWarnings} inbox(es) at risk. Monitor closely.
            </span>
          )}
          {trend === 'stable' && currentWeekDeaths > 5 && (
            <span className="text-amber-600 font-medium">
              Consistent high death rate. Consider infrastructure review.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
