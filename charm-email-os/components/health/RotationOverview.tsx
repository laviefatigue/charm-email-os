'use client';

import { RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { DomainHealthMetrics, OverallBackupCapacity } from '@/lib/types/health';
import { getRotationAttentionItems } from '@/lib/types/health';
import { DomainPhaseDistribution } from './DomainPhaseDistribution';
import { RotationNeedsAttention } from './RotationNeedsAttention';

interface RotationOverviewProps {
  domains: DomainHealthMetrics[];
  backupCapacity: OverallBackupCapacity | null;
  onOrderReplacement?: (domainId: string) => void;
  className?: string;
}

export function RotationOverview({
  domains,
  backupCapacity,
  onOrderReplacement,
  className,
}: RotationOverviewProps) {
  const rotationItems = getRotationAttentionItems(domains);
  const criticalCount = rotationItems.filter(i => i.urgency === 'critical').length;
  const hasRotationNeeds = rotationItems.length > 0;

  // Determine overall status
  const overallStatus = criticalCount > 0 ? 'critical' :
                        rotationItems.length > 0 ? 'warning' : 'healthy';

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Rotation Overview
          </CardTitle>
          <Badge
            variant={
              overallStatus === 'healthy' ? 'default' :
              overallStatus === 'warning' ? 'secondary' : 'destructive'
            }
            className={cn(
              overallStatus === 'warning' && 'bg-amber-100 text-amber-800 hover:bg-amber-200',
              overallStatus === 'healthy' && 'bg-green-100 text-green-800 hover:bg-green-200'
            )}
          >
            {overallStatus === 'healthy' ? (
              <><CheckCircle className="h-3 w-3 mr-1" /> All Good</>
            ) : overallStatus === 'warning' ? (
              <><AlertTriangle className="h-3 w-3 mr-1" /> Attention Needed</>
            ) : (
              <><AlertTriangle className="h-3 w-3 mr-1" /> Rotation Required</>
            )}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Domain Phase Distribution */}
        <DomainPhaseDistribution domains={domains} />

        {/* Spare Capacity Summary (if available) */}
        {backupCapacity && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Spare Capacity</h4>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-muted-foreground">
                    {backupCapacity.warmingPipeline.count} spare / {backupCapacity.warmingPipeline.targetCount} target
                  </span>
                  <span className={cn(
                    'font-medium',
                    backupCapacity.warmingPipeline.status === 'healthy' && 'text-green-600',
                    backupCapacity.warmingPipeline.status === 'warning' && 'text-amber-600',
                    backupCapacity.warmingPipeline.status === 'critical' && 'text-red-600'
                  )}>
                    {Math.round(backupCapacity.warmingPipeline.percentage)}%
                  </span>
                </div>
                <Progress
                  value={Math.min(backupCapacity.warmingPipeline.percentage, 100)}
                  className={cn(
                    'h-2',
                    backupCapacity.warmingPipeline.status === 'healthy' && '[&>div]:bg-green-500',
                    backupCapacity.warmingPipeline.status === 'warning' && '[&>div]:bg-amber-500',
                    backupCapacity.warmingPipeline.status === 'critical' && '[&>div]:bg-red-500'
                  )}
                />
              </div>
              <Badge
                variant="outline"
                className={cn(
                  'shrink-0',
                  backupCapacity.warmingPipeline.status === 'healthy' && 'border-green-300 text-green-700',
                  backupCapacity.warmingPipeline.status === 'warning' && 'border-amber-300 text-amber-700',
                  backupCapacity.warmingPipeline.status === 'critical' && 'border-red-300 text-red-700'
                )}
              >
                {backupCapacity.warmingPipeline.status === 'healthy' ? 'Healthy' :
                 backupCapacity.warmingPipeline.status === 'warning' ? 'Low' : 'Critical'}
              </Badge>
            </div>
            {backupCapacity.warmingPipeline.status !== 'healthy' && (
              <p className="text-xs text-muted-foreground">
                {backupCapacity.warmingPipeline.status === 'warning'
                  ? 'Spare capacity is below target. Consider ordering more inboxes.'
                  : 'Critical: Insufficient spare capacity for replacements.'}
              </p>
            )}
          </div>
        )}

        {/* Domains Needing Rotation */}
        <div className="pt-2 border-t">
          <RotationNeedsAttention
            domains={domains}
            onOrderReplacement={onOrderReplacement}
          />
        </div>
      </CardContent>
    </Card>
  );
}
