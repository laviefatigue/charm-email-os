'use client';

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { LifecycleDistribution, PoolStatus } from '@/lib/types/health';
import { POOL_STATUS_CONFIG } from '@/lib/types/health';

interface LifecycleDistributionChartProps {
  distribution: LifecycleDistribution;
  onSegmentClick?: (status: PoolStatus) => void;
  selectedStatus?: PoolStatus | null;
  className?: string;
  size?: number;
}

/**
 * Lifecycle Distribution Chart - Shows inbox pool status breakdown
 *
 * Displays:
 * - Deployed: Inboxes currently in active campaigns
 * - Reserve: Ready pool, not assigned to campaigns
 * - Warning: Has recent bounces, needs cooldown
 *
 * Note: Excludes dead inboxes from the pie chart (shown separately)
 */
export function LifecycleDistributionChart({
  distribution,
  onSegmentClick,
  selectedStatus,
  className,
  size = 200,
}: LifecycleDistributionChartProps) {
  const { totalLive, deployed, reserve, warning, dead, incubating, active } = distribution;

  // Calculate percentages and conic gradient stops for pool status
  const segments = useMemo(() => {
    if (totalLive === 0) return [];

    const statuses: PoolStatus[] = ['deployed', 'reserve', 'warning'];
    const result: Array<{
      status: PoolStatus;
      count: number;
      percentage: number;
      startAngle: number;
      endAngle: number;
      color: string;
    }> = [];

    let currentAngle = 0;

    for (const status of statuses) {
      const count = distribution[status];
      if (count === 0) continue;

      const percentage = (count / totalLive) * 100;
      const angle = (percentage / 100) * 360;

      result.push({
        status,
        count,
        percentage,
        startAngle: currentAngle,
        endAngle: currentAngle + angle,
        color: POOL_STATUS_CONFIG[status].color,
      });

      currentAngle += angle;
    }

    return result;
  }, [distribution, totalLive]);

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

  // Handle segment click
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSegmentClick || segments.length === 0) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const x = e.clientX - rect.left - centerX;
    const y = e.clientY - rect.top - centerY;

    let angle = Math.atan2(x, -y) * (180 / Math.PI);
    if (angle < 0) angle += 360;

    for (const seg of segments) {
      if (angle >= seg.startAngle && angle < seg.endAngle) {
        onSegmentClick(seg.status);
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
            <div className="text-3xl font-bold">{totalLive}</div>
            <div className="text-sm text-muted-foreground">Live Inboxes</div>
          </div>
        </div>
      </div>

      {/* Pool Status Legend */}
      <div className="space-y-2 w-full">
        <h4 className="text-sm font-medium text-muted-foreground">Pool Status</h4>
        <div className="grid grid-cols-3 gap-2">
          {(['deployed', 'reserve', 'warning'] as PoolStatus[]).map((status) => {
            const count = distribution[status];
            const percentage = totalLive > 0 ? ((count / totalLive) * 100).toFixed(1) : '0';
            const isSelected = selectedStatus === status;
            const { label, color } = POOL_STATUS_CONFIG[status];

            return (
              <button
                key={status}
                onClick={() => onSegmentClick?.(status)}
                className={cn(
                  'flex flex-col items-center p-2 rounded-md transition-colors text-center',
                  'hover:bg-muted/50',
                  isSelected && 'bg-muted ring-1 ring-primary'
                )}
              >
                <div
                  className="w-3 h-3 rounded-full mb-1"
                  style={{ backgroundColor: color }}
                />
                <span className="text-lg font-semibold">{count}</span>
                <span className="text-xs text-muted-foreground">{label}</span>
                <span className="text-xs text-muted-foreground">{percentage}%</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Lifecycle Stats */}
      <div className="space-y-2 w-full border-t pt-3">
        <h4 className="text-sm font-medium text-muted-foreground">Lifecycle</h4>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="p-2 rounded-md bg-blue-50">
            <span className="text-lg font-semibold text-blue-700">{incubating}</span>
            <div className="text-xs text-blue-600">Incubating</div>
            <div className="text-xs text-muted-foreground">{'< 14 days'}</div>
          </div>
          <div className="p-2 rounded-md bg-green-50">
            <span className="text-lg font-semibold text-green-700">{active}</span>
            <div className="text-xs text-green-600">Active</div>
            <div className="text-xs text-muted-foreground">Mature</div>
          </div>
          <div className="p-2 rounded-md bg-gray-50">
            <span className="text-lg font-semibold text-gray-700">{dead}</span>
            <div className="text-xs text-gray-600">Dead</div>
            <div className="text-xs text-muted-foreground">Killed</div>
          </div>
        </div>
      </div>

      {/* Selected filter indicator */}
      {selectedStatus && (
        <div className="text-sm text-muted-foreground">
          Showing: <span className="font-medium">{POOL_STATUS_CONFIG[selectedStatus].label}</span> inboxes
          <button
            onClick={() => onSegmentClick?.(selectedStatus)}
            className="ml-2 text-primary hover:underline"
          >
            Clear filter
          </button>
        </div>
      )}
    </div>
  );
}
