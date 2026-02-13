'use client';

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';

export type HealthRange = 'healthy' | 'good' | 'warning' | 'critical';

export interface HealthDistribution {
  healthy: number;   // 80-100
  good: number;      // 60-80
  warning: number;   // 40-60
  critical: number;  // 0-40
  total: number;
}

interface HealthDistributionPieChartProps {
  distribution: HealthDistribution;
  onSegmentClick?: (range: HealthRange) => void;
  selectedRange?: HealthRange | null;
  className?: string;
  size?: number;
}

// Base colors for each health range
const HEALTH_COLORS: Record<HealthRange, { base: string; light: string; dark: string }> = {
  healthy: {
    base: 'rgb(34, 197, 94)',      // green-500
    light: 'rgb(134, 239, 172)',   // green-300
    dark: 'rgb(22, 163, 74)',      // green-600
  },
  good: {
    base: 'rgb(234, 179, 8)',      // yellow-500
    light: 'rgb(253, 224, 71)',    // yellow-300
    dark: 'rgb(202, 138, 4)',      // yellow-600
  },
  warning: {
    base: 'rgb(249, 115, 22)',     // orange-500
    light: 'rgb(253, 186, 116)',   // orange-300
    dark: 'rgb(234, 88, 12)',      // orange-600
  },
  critical: {
    base: 'rgb(239, 68, 68)',      // red-500
    light: 'rgb(252, 165, 165)',   // red-300
    dark: 'rgb(220, 38, 38)',      // red-600
  },
};

const HEALTH_LABELS: Record<HealthRange, { label: string; range: string }> = {
  healthy: { label: 'Healthy', range: '80-100' },
  good: { label: 'Good', range: '60-80' },
  warning: { label: 'Warning', range: '40-60' },
  critical: { label: 'Critical', range: '0-40' },
};

export function HealthDistributionPieChart({
  distribution,
  onSegmentClick,
  selectedRange,
  className,
  size = 240,
}: HealthDistributionPieChartProps) {
  const { total } = distribution;

  // Calculate percentages and conic gradient stops
  const segments = useMemo(() => {
    if (total === 0) return [];

    const ranges: HealthRange[] = ['critical', 'warning', 'good', 'healthy'];
    const result: Array<{
      range: HealthRange;
      count: number;
      percentage: number;
      startAngle: number;
      endAngle: number;
      color: string;
    }> = [];

    let currentAngle = 0;

    // Calculate max count for density-based coloring
    const maxCount = Math.max(
      distribution.healthy,
      distribution.good,
      distribution.warning,
      distribution.critical
    );

    for (const range of ranges) {
      const count = distribution[range];
      if (count === 0) continue;

      const percentage = (count / total) * 100;
      const angle = (percentage / 100) * 360;

      // Density-based color: darker if more inboxes in this range
      const density = maxCount > 0 ? count / maxCount : 0;
      const colors = HEALTH_COLORS[range];
      // Interpolate between light and dark based on density
      const color = density > 0.7 ? colors.dark : density > 0.3 ? colors.base : colors.light;

      result.push({
        range,
        count,
        percentage,
        startAngle: currentAngle,
        endAngle: currentAngle + angle,
        color,
      });

      currentAngle += angle;
    }

    return result;
  }, [distribution, total]);

  // Generate conic-gradient CSS
  const gradientStyle = useMemo(() => {
    if (segments.length === 0) {
      return { background: 'rgb(229, 231, 235)' }; // gray-200 for empty
    }

    const stops = segments
      .map((seg) => `${seg.color} ${seg.startAngle}deg ${seg.endAngle}deg`)
      .join(', ');

    return { background: `conic-gradient(from 0deg, ${stops})` };
  }, [segments]);

  // Handle segment click - determine which segment was clicked based on angle
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSegmentClick || segments.length === 0) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const x = e.clientX - rect.left - centerX;
    const y = e.clientY - rect.top - centerY;

    // Calculate angle from center (0 degrees at top, clockwise)
    let angle = Math.atan2(x, -y) * (180 / Math.PI);
    if (angle < 0) angle += 360;

    // Find which segment was clicked
    for (const seg of segments) {
      if (angle >= seg.startAngle && angle < seg.endAngle) {
        onSegmentClick(seg.range);
        return;
      }
    }
  };

  return (
    <div className={cn('flex flex-col items-center gap-4', className)}>
      {/* Pie Chart */}
      <div
        className={cn(
          'relative rounded-full cursor-pointer transition-transform hover:scale-[1.02]',
          'shadow-lg'
        )}
        style={{
          width: size,
          height: size,
          ...gradientStyle,
        }}
        onClick={handleClick}
      >
        {/* Inner circle for donut effect */}
        <div
          className="absolute bg-background rounded-full flex items-center justify-center"
          style={{
            width: size * 0.6,
            height: size * 0.6,
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
          }}
        >
          <div className="text-center">
            <div className="text-3xl font-bold">{total}</div>
            <div className="text-sm text-muted-foreground">Total Inboxes</div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        {(['critical', 'warning', 'good', 'healthy'] as HealthRange[]).map((range) => {
          const count = distribution[range];
          const percentage = total > 0 ? ((count / total) * 100).toFixed(1) : '0';
          const isSelected = selectedRange === range;
          const { label, range: scoreRange } = HEALTH_LABELS[range];

          return (
            <button
              key={range}
              onClick={() => onSegmentClick?.(range)}
              className={cn(
                'flex items-center gap-2 px-2 py-1 rounded-md transition-colors text-left',
                'hover:bg-muted/50',
                isSelected && 'bg-muted ring-1 ring-primary'
              )}
            >
              <div
                className="w-3 h-3 rounded-sm flex-shrink-0"
                style={{ backgroundColor: HEALTH_COLORS[range].base }}
              />
              <div className="flex flex-col">
                <span className="text-sm font-medium">
                  {label}: {count}
                </span>
                <span className="text-xs text-muted-foreground">
                  {percentage}% ({scoreRange})
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected filter indicator */}
      {selectedRange && (
        <div className="text-sm text-muted-foreground">
          Showing: <span className="font-medium">{HEALTH_LABELS[selectedRange].label}</span> inboxes
          <button
            onClick={() => onSegmentClick?.(selectedRange)}
            className="ml-2 text-primary hover:underline"
          >
            Clear filter
          </button>
        </div>
      )}
    </div>
  );
}
