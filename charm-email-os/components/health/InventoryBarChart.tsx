'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { CheckCircle, AlertTriangle, Shield } from 'lucide-react';
import {
  InventoryBarChartData,
  InventoryPoolStatus,
  InventoryLifecycleStatus,
  POOL_STATUS_CONFIG,
  LIFECYCLE_STATUS_CONFIG,
  CapacityStatus,
  CAPACITY_STATUS_CONFIG,
} from '@/lib/types/inventory';

interface InventoryBarChartProps {
  data: InventoryBarChartData;
  lifecycleCounts: {
    active: number;
    incubating: number;
    dead: number;
  };
  autoKillEnabled: boolean;
  onPoolStatusClick?: (status: InventoryPoolStatus) => void;
  onLifecycleStatusClick?: (status: InventoryLifecycleStatus) => void;
  className?: string;
}

export function InventoryBarChart({
  data,
  lifecycleCounts,
  autoKillEnabled,
  onPoolStatusClick,
  onLifecycleStatusClick,
  className,
}: InventoryBarChartProps) {
  // Calculate percentages for the bar
  const percentages = useMemo(() => {
    if (data.total === 0) {
      return { deployed: 0, warning: 0, reserve: 0 };
    }
    return {
      deployed: (data.deployed / data.total) * 100,
      warning: (data.warning / data.total) * 100,
      reserve: (data.reserve / data.total) * 100,
    };
  }, [data]);

  // Calculate target line positions
  const targetPositions = useMemo(() => {
    if (data.total === 0) {
      return { deployed: 0, reserve: 0 };
    }
    return {
      deployed: (data.deployedTarget / data.total) * 100,
      reserve: ((data.total - data.reserveTarget) / data.total) * 100,
    };
  }, [data]);

  const capacityConfig = CAPACITY_STATUS_CONFIG[data.capacityStatus];
  const CapacityIcon = data.capacityStatus === 'healthy' ? CheckCircle : AlertTriangle;

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Inventory Distribution</CardTitle>
          <div className="flex items-center gap-2">
            {/* Auto-Kill Status Badge */}
            <Badge
              variant={autoKillEnabled ? 'default' : 'secondary'}
              className={cn(
                'gap-1',
                autoKillEnabled ? 'bg-emerald-600 hover:bg-emerald-700' : ''
              )}
            >
              <Shield className="w-3 h-3" />
              Auto-Kill {autoKillEnabled ? 'ON' : 'OFF'}
            </Badge>
            {/* Capacity Status Badge */}
            <Badge
              variant="outline"
              className={cn('gap-1', capacityConfig.color, capacityConfig.bg)}
            >
              <CapacityIcon className="w-3 h-3" />
              {capacityConfig.label}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Main Stacked Bar */}
        <div className="space-y-2">
          <div className="relative h-10 bg-muted rounded-lg overflow-hidden">
            <TooltipProvider>
              {/* Deployed Section */}
              {percentages.deployed > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onPoolStatusClick?.('deployed')}
                      className={cn(
                        'absolute h-full transition-all hover:brightness-110',
                        POOL_STATUS_CONFIG.deployed.bg
                      )}
                      style={{
                        left: 0,
                        width: `${percentages.deployed}%`,
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="font-medium">Deployed: {data.deployed}</p>
                    <p className="text-xs text-muted-foreground">
                      {POOL_STATUS_CONFIG.deployed.description}
                    </p>
                  </TooltipContent>
                </Tooltip>
              )}

              {/* Warning Section */}
              {percentages.warning > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onPoolStatusClick?.('warning')}
                      className={cn(
                        'absolute h-full transition-all hover:brightness-110',
                        POOL_STATUS_CONFIG.warning.bg
                      )}
                      style={{
                        left: `${percentages.deployed}%`,
                        width: `${percentages.warning}%`,
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="font-medium">Warning: {data.warning}</p>
                    <p className="text-xs text-muted-foreground">
                      {POOL_STATUS_CONFIG.warning.description}
                    </p>
                  </TooltipContent>
                </Tooltip>
              )}

              {/* Reserve Section */}
              {percentages.reserve > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onPoolStatusClick?.('reserve')}
                      className={cn(
                        'absolute h-full transition-all hover:brightness-110',
                        POOL_STATUS_CONFIG.reserve.bg
                      )}
                      style={{
                        left: `${percentages.deployed + percentages.warning}%`,
                        width: `${percentages.reserve}%`,
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="font-medium">Reserve: {data.reserve}</p>
                    <p className="text-xs text-muted-foreground">
                      {POOL_STATUS_CONFIG.reserve.description}
                    </p>
                  </TooltipContent>
                </Tooltip>
              )}
            </TooltipProvider>

            {/* Target Lines */}
            {data.deployedTarget > 0 && (
              <div
                className="absolute top-0 h-full w-0.5 bg-green-900 z-10"
                style={{ left: `${targetPositions.deployed}%` }}
              >
                <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] text-green-900 whitespace-nowrap">
                  Target: {data.deployedTarget}
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-4">
              <button
                onClick={() => onPoolStatusClick?.('deployed')}
                className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
              >
                <div className={cn('w-3 h-3 rounded-sm', POOL_STATUS_CONFIG.deployed.bg)} />
                <span className="font-medium">{data.deployed}</span>
                <span className="text-muted-foreground">Deployed</span>
              </button>
              <button
                onClick={() => onPoolStatusClick?.('warning')}
                className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
              >
                <div className={cn('w-3 h-3 rounded-sm', POOL_STATUS_CONFIG.warning.bg)} />
                <span className="font-medium">{data.warning}</span>
                <span className="text-muted-foreground">Warning</span>
              </button>
              <button
                onClick={() => onPoolStatusClick?.('reserve')}
                className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
              >
                <div className={cn('w-3 h-3 rounded-sm', POOL_STATUS_CONFIG.reserve.bg)} />
                <span className="font-medium">{data.reserve}</span>
                <span className="text-muted-foreground">Reserve</span>
              </button>
            </div>
            <div className="text-muted-foreground">
              Total: <span className="font-medium text-foreground">{data.total}</span>
            </div>
          </div>
        </div>

        {/* Spare Capacity Indicator */}
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Spare Capacity:</span>
            <span className={cn('font-semibold', capacityConfig.color)}>
              {data.spareCapacity} ({data.sparePercentage.toFixed(1)}%)
            </span>
          </div>
          <div className="text-xs text-muted-foreground">
            {data.capacityStatus === 'healthy' && 'Healthy reserve for campaign scaling'}
            {data.capacityStatus === 'warning' && 'Consider adding more inboxes soon'}
            {data.capacityStatus === 'critical' && 'Low capacity - add inboxes immediately'}
          </div>
        </div>

        {/* Lifecycle Breakdown */}
        <div className="space-y-2">
          <div className="text-sm font-medium text-muted-foreground">Lifecycle Status</div>
          <div className="flex items-center gap-3">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onLifecycleStatusClick?.('active')}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all hover:ring-2 hover:ring-offset-1',
                      LIFECYCLE_STATUS_CONFIG.active.bg,
                      LIFECYCLE_STATUS_CONFIG.active.text
                    )}
                  >
                    <span className="font-semibold">{lifecycleCounts.active}</span>
                    <span className="text-sm">Active</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{LIFECYCLE_STATUS_CONFIG.active.description}</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onLifecycleStatusClick?.('incubating')}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all hover:ring-2 hover:ring-offset-1',
                      LIFECYCLE_STATUS_CONFIG.incubating.bg,
                      LIFECYCLE_STATUS_CONFIG.incubating.text
                    )}
                  >
                    <span className="font-semibold">{lifecycleCounts.incubating}</span>
                    <span className="text-sm">Incubating</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{LIFECYCLE_STATUS_CONFIG.incubating.description}</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onLifecycleStatusClick?.('dead')}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all hover:ring-2 hover:ring-offset-1',
                      LIFECYCLE_STATUS_CONFIG.dead.bg,
                      LIFECYCLE_STATUS_CONFIG.dead.text
                    )}
                  >
                    <span className="font-semibold">{lifecycleCounts.dead}</span>
                    <span className="text-sm">Dead</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{LIFECYCLE_STATUS_CONFIG.dead.description}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
