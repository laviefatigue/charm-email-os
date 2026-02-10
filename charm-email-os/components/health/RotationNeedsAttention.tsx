'use client';

import { AlertTriangle, Clock, Inbox, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { DomainHealthMetrics, RotationAttentionItem } from '@/lib/types/health';
import { getRotationAttentionItems, PHASE_COLORS } from '@/lib/types/health';
import { DomainPhaseBadge } from './DomainPhaseBadge';

interface RotationNeedsAttentionProps {
  domains: DomainHealthMetrics[];
  onOrderReplacement?: (domainId: string) => void;
  className?: string;
}

const URGENCY_CONFIG = {
  critical: {
    icon: AlertTriangle,
    iconColor: 'text-red-500',
    bgColor: 'bg-red-50',
    action: 'Order Replacement',
    actionVariant: 'destructive' as const,
  },
  warning: {
    icon: Clock,
    iconColor: 'text-amber-500',
    bgColor: 'bg-amber-50',
    action: 'Plan Migration',
    actionVariant: 'outline' as const,
  },
  monitor: {
    icon: RefreshCw,
    iconColor: 'text-blue-500',
    bgColor: 'bg-blue-50',
    action: 'Monitor',
    actionVariant: 'ghost' as const,
  },
};

export function RotationNeedsAttention({
  domains,
  onOrderReplacement,
  className,
}: RotationNeedsAttentionProps) {
  const items = getRotationAttentionItems(domains);

  if (items.length === 0) {
    return (
      <div className={cn('text-sm text-muted-foreground text-center py-4', className)}>
        <RefreshCw className="h-5 w-5 mx-auto mb-2 text-green-500" />
        No domains approaching rotation
      </div>
    );
  }

  const criticalCount = items.filter(i => i.urgency === 'critical').length;
  const warningCount = items.filter(i => i.urgency === 'warning').length;

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500" />
        <h4 className="text-sm font-medium">Needs Rotation</h4>
        <span className="text-xs text-muted-foreground">({items.length} domains)</span>
        {criticalCount > 0 && (
          <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
            {criticalCount} critical
          </span>
        )}
        {warningCount > 0 && (
          <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
            {warningCount} warning
          </span>
        )}
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {items.map(item => {
          const config = URGENCY_CONFIG[item.urgency];
          const Icon = config.icon;

          return (
            <div
              key={item.domainId}
              className={cn(
                'flex items-center gap-3 p-3 rounded-lg border',
                config.bgColor
              )}
            >
              <Icon className={cn('h-5 w-5 shrink-0', config.iconColor)} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">{item.domain}</span>
                  <DomainPhaseBadge phase={item.phase} />
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {item.ageInDays} days old
                  </span>
                  {item.daysUntilRotation > 0 && (
                    <span>{item.daysUntilRotation}d until rotation</span>
                  )}
                  <span className="flex items-center gap-1">
                    <Inbox className="h-3 w-3" />
                    {item.inboxCount} inboxes
                  </span>
                </div>
              </div>

              {onOrderReplacement && (
                <Button
                  size="sm"
                  variant={config.actionVariant}
                  onClick={() => onOrderReplacement(item.domainId)}
                  className="shrink-0"
                >
                  {config.action}
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
