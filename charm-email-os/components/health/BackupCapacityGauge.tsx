'use client';

import { Database, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { OverallBackupCapacity, BackupCapacityStatus } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface BackupCapacityGaugeProps {
  capacity: OverallBackupCapacity | null;
}

function CapacityBar({ tier }: { tier: BackupCapacityStatus }) {
  const statusIcon = {
    healthy: CheckCircle,
    warning: AlertTriangle,
    critical: XCircle,
  };
  const StatusIcon = statusIcon[tier.status];

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <StatusIcon
            className={cn(
              'h-4 w-4',
              tier.status === 'healthy' && 'text-green-600',
              tier.status === 'warning' && 'text-yellow-600',
              tier.status === 'critical' && 'text-red-600'
            )}
          />
          <span className="font-medium">{tier.label}</span>
        </div>
        <span className="text-muted-foreground">
          {tier.count} / {tier.targetCount}
          <span className="ml-1 text-xs">({Math.round(tier.percentage)}%)</span>
        </span>
      </div>
      <div className="h-4 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            tier.status === 'healthy' && 'bg-green-500',
            tier.status === 'warning' && 'bg-yellow-500',
            tier.status === 'critical' && 'bg-red-500'
          )}
          style={{ width: `${Math.min(tier.percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}

export function BackupCapacityGauge({ capacity }: BackupCapacityGaugeProps) {
  if (!capacity) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Backup Capacity
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <Database className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p>Loading capacity data...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Backup Capacity
          </CardTitle>
          <Badge
            variant={
              capacity.overallStatus === 'healthy'
                ? 'default'
                : capacity.overallStatus === 'warning'
                ? 'secondary'
                : 'destructive'
            }
            className={cn(
              capacity.overallStatus === 'warning' &&
                'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
            )}
          >
            {capacity.overallStatus.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Primary Tier */}
        <CapacityBar tier={capacity.primary} />

        {/* Hot Backup Tier */}
        <CapacityBar tier={capacity.hotBackup} />

        {/* Warming Pipeline Tier */}
        <CapacityBar tier={capacity.warmingPipeline} />

        {/* Summary Stats */}
        <div className="pt-3 border-t grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-xl font-bold">{capacity.totalCapacity}</div>
            <div className="text-xs text-muted-foreground">Total Capacity</div>
          </div>
          <div>
            <div className="text-xl font-bold">{capacity.activeCapacity}</div>
            <div className="text-xs text-muted-foreground">Active</div>
          </div>
          <div>
            <div
              className={cn(
                'text-xl font-bold',
                capacity.backupRatio >= 1 ? 'text-green-600' : 'text-yellow-600'
              )}
            >
              {Math.round(capacity.backupRatio * 100)}%
            </div>
            <div className="text-xs text-muted-foreground">Backup Ratio</div>
          </div>
        </div>

        {/* Warning Message */}
        {capacity.overallStatus !== 'healthy' && (
          <div
            className={cn(
              'p-3 rounded-lg text-sm',
              capacity.overallStatus === 'warning'
                ? 'bg-yellow-50 text-yellow-800 border border-yellow-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            )}
          >
            {capacity.overallStatus === 'warning' ? (
              <span>
                <AlertTriangle className="h-4 w-4 inline mr-1" />
                Backup capacity below target. Consider adding more warming inboxes.
              </span>
            ) : (
              <span>
                <XCircle className="h-4 w-4 inline mr-1" />
                Critical: Backup capacity insufficient. Add inboxes immediately.
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
