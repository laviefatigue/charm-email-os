'use client';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, AlertCircle } from 'lucide-react';

type TrendDirection = 'up' | 'down' | 'stable';
type StatusType = 'healthy' | 'warning' | 'critical' | 'neutral';

interface KPICardProps {
  value: string | number;
  label: string;
  subtext?: string;
  trend?: TrendDirection;
  trendValue?: string;
  status?: StatusType;
  icon?: React.ReactNode;
  className?: string;
}

const STATUS_CONFIG: Record<StatusType, { bg: string; text: string; icon: React.ReactNode }> = {
  healthy: {
    bg: 'bg-green-50 border-green-200',
    text: 'text-green-700',
    icon: <CheckCircle className="w-4 h-4 text-green-600" />,
  },
  warning: {
    bg: 'bg-amber-50 border-amber-200',
    text: 'text-amber-700',
    icon: <AlertTriangle className="w-4 h-4 text-amber-600" />,
  },
  critical: {
    bg: 'bg-red-50 border-red-200',
    text: 'text-red-700',
    icon: <AlertCircle className="w-4 h-4 text-red-600" />,
  },
  neutral: {
    bg: 'bg-slate-50 border-slate-200',
    text: 'text-slate-700',
    icon: null,
  },
};

const TREND_CONFIG: Record<TrendDirection, { icon: React.ReactNode; color: string }> = {
  up: {
    icon: <TrendingUp className="w-3 h-3" />,
    color: 'text-green-600',
  },
  down: {
    icon: <TrendingDown className="w-3 h-3" />,
    color: 'text-red-600',
  },
  stable: {
    icon: <Minus className="w-3 h-3" />,
    color: 'text-slate-500',
  },
};

export function KPICard({
  value,
  label,
  subtext,
  trend,
  trendValue,
  status = 'neutral',
  icon,
  className,
}: KPICardProps) {
  const statusConfig = STATUS_CONFIG[status];
  const trendConfig = trend ? TREND_CONFIG[trend] : null;

  return (
    <Card className={cn('border', statusConfig.bg, className)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            {/* Label */}
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {label}
            </p>

            {/* Main Value */}
            <div className="flex items-baseline gap-2">
              <span className={cn('text-2xl font-bold', statusConfig.text)}>
                {value}
              </span>

              {/* Trend Indicator */}
              {trendConfig && (
                <div className={cn('flex items-center gap-0.5 text-xs', trendConfig.color)}>
                  {trendConfig.icon}
                  {trendValue && <span>{trendValue}</span>}
                </div>
              )}
            </div>

            {/* Subtext */}
            {subtext && (
              <p className="text-xs text-muted-foreground">{subtext}</p>
            )}
          </div>

          {/* Status Icon or Custom Icon */}
          <div className="flex-shrink-0">
            {icon || statusConfig.icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
