'use client';

import { AlertTriangle, Clock, Skull, CheckCircle, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { KillTrigger } from '@/lib/types/health';
import { KILL_TRIGGER_THRESHOLDS } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface KillTriggerCardProps {
  trigger: KillTrigger;
  onExecute?: (triggerId: string) => void;
  onDismiss?: (triggerId: string) => void;
  onRetest?: (triggerId: string) => void;
  isExecuting?: boolean;
}

export function KillTriggerCard({
  trigger,
  onExecute,
  onDismiss,
  onRetest,
  isExecuting = false,
}: KillTriggerCardProps) {
  const isInstant = trigger.severity === 'instant';
  const threshold = KILL_TRIGGER_THRESHOLDS[trigger.type];
  const isResolved = trigger.actionTaken === 'killed' || trigger.actionTaken === 'dismissed';
  const isPending = trigger.actionTaken === 'pending';

  const formatTimeAgo = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - new Date(date).getTime();
    const minutes = Math.floor(diff / (1000 * 60));
    const hours = Math.floor(diff / (1000 * 60 * 60));

    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const formatRetestTime = (date: Date) => {
    const now = new Date();
    const diff = new Date(date).getTime() - now.getTime();
    const hours = Math.ceil(diff / (1000 * 60 * 60));

    if (hours <= 0) return 'Retesting now...';
    return `Retest in ${hours}h`;
  };

  return (
    <div
      className={cn(
        'p-4 rounded-lg border transition-all',
        isResolved && 'opacity-60',
        !isResolved && isInstant && 'border-red-300 bg-red-50',
        !isResolved && !isInstant && 'border-yellow-300 bg-yellow-50',
        isResolved && 'border-gray-200 bg-gray-50'
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Header with severity badge */}
          <div className="flex items-center gap-2 mb-2">
            {trigger.actionTaken === 'killed' ? (
              <Skull className="h-4 w-4 text-gray-500 flex-shrink-0" />
            ) : isInstant ? (
              <Skull className="h-4 w-4 text-red-600 flex-shrink-0" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-yellow-600 flex-shrink-0" />
            )}

            {trigger.actionTaken === 'killed' ? (
              <Badge variant="secondary" className="bg-gray-200 text-gray-700">
                KILLED
              </Badge>
            ) : isInstant ? (
              <Badge variant="destructive" className="font-semibold">
                INSTANT KILL
              </Badge>
            ) : (
              <Badge
                variant="secondary"
                className="bg-yellow-200 text-yellow-800 font-semibold"
              >
                CONFIRMING
              </Badge>
            )}

            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatTimeAgo(trigger.detectedAt)}
            </span>
          </div>

          {/* Inbox info */}
          <div className="font-medium text-sm truncate">{trigger.inboxEmail}</div>
          <div className="text-xs text-muted-foreground mt-0.5">{trigger.domainName}</div>

          {/* Trigger details */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium px-2 py-1 rounded bg-white/50">
              {threshold.label}
            </span>
            <span className="text-xs text-muted-foreground">
              {trigger.value.toFixed(trigger.value < 1 ? 2 : 0)} / {trigger.threshold}
              {threshold.minSends && <span className="ml-1">(min {threshold.minSends} sends)</span>}
            </span>
          </div>

          {/* Status indicator */}
          {trigger.actionTaken === 'killed' && trigger.resolvedAt && (
            <div className="mt-2 text-xs flex items-center gap-1 text-gray-600">
              <CheckCircle className="h-3 w-3" />
              Killed {formatTimeAgo(trigger.resolvedAt)}
            </div>
          )}

          {/* Retest countdown for confirming triggers */}
          {!isResolved && !isInstant && trigger.retestAt && (
            <div className="mt-2 text-xs flex items-center gap-1 text-yellow-700">
              <Clock className="h-3 w-3" />
              {formatRetestTime(trigger.retestAt)}
            </div>
          )}

          {/* Action buttons for pending triggers */}
          {isPending && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {isInstant ? (
                // Instant kill triggers - primary action is Execute Kill
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => onExecute?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-8"
                >
                  <Skull className="h-3.5 w-3.5 mr-1.5" />
                  {isExecuting ? 'Killing...' : 'Execute Kill'}
                </Button>
              ) : (
                // Confirming triggers - multiple options
                <>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onExecute?.(trigger.id)}
                    disabled={isExecuting}
                    className="h-8"
                  >
                    <Skull className="h-3.5 w-3.5 mr-1.5" />
                    {isExecuting ? 'Killing...' : 'Kill Now'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onRetest?.(trigger.id)}
                    disabled={isExecuting}
                    className="h-8"
                  >
                    <Clock className="h-3.5 w-3.5 mr-1.5" />
                    Retest in 48h
                  </Button>
                </>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDismiss?.(trigger.id)}
                disabled={isExecuting}
                className="h-8 text-muted-foreground"
              >
                <X className="h-3.5 w-3.5 mr-1.5" />
                Dismiss
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
