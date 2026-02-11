'use client';

import { Skull, AlertTriangle, Clock, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { KillTrigger } from '@/lib/types/health';
import { KILL_TRIGGER_THRESHOLDS } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface KillTriggerTableProps {
  triggers: KillTrigger[];
  onExecute?: (triggerId: string) => void;
  onDismiss?: (triggerId: string) => void;
  onRetest?: (triggerId: string) => void;
  executingTriggerIds?: string[];
}

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - new Date(date).getTime();
  const minutes = Math.floor(diff / (1000 * 60));
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);

  if (minutes < 60) return `${minutes}m`;
  if (hours < 24) return `${hours}h`;
  return `${days}d`;
}

function SeverityBadge({ trigger }: { trigger: KillTrigger }) {
  const isInstant = trigger.severity === 'instant';
  const isKilled = trigger.actionTaken === 'killed';

  if (isKilled) {
    return (
      <Badge variant="secondary" className="bg-gray-200 text-gray-600 text-xs px-1.5">
        KILLED
      </Badge>
    );
  }

  if (isInstant) {
    return (
      <Badge variant="destructive" className="text-xs px-1.5">
        INSTANT
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" className="bg-yellow-100 text-yellow-800 text-xs px-1.5">
      CONFIRM
    </Badge>
  );
}

function TriggerRow({
  trigger,
  onExecute,
  onDismiss,
  onRetest,
  isExecuting,
}: {
  trigger: KillTrigger;
  onExecute?: (triggerId: string) => void;
  onDismiss?: (triggerId: string) => void;
  onRetest?: (triggerId: string) => void;
  isExecuting?: boolean;
}) {
  const threshold = KILL_TRIGGER_THRESHOLDS[trigger.type];
  const isInstant = trigger.severity === 'instant';
  const isPending = trigger.actionTaken === 'pending';
  const isKilled = trigger.actionTaken === 'killed';

  const formatValue = (value: number, threshold: number) => {
    const valStr = value < 1 ? value.toFixed(2) : value.toFixed(0);
    const thrStr = threshold < 1 ? threshold.toFixed(2) : threshold.toFixed(0);
    return `${valStr}/${thrStr}`;
  };

  return (
    <tr
      className={cn(
        'border-b last:border-b-0 transition-colors',
        isKilled && 'opacity-50 bg-gray-50',
        !isKilled && isInstant && 'bg-red-50/50',
        !isKilled && !isInstant && 'bg-yellow-50/50'
      )}
    >
      {/* Severity */}
      <td className="py-2 px-3 w-[90px]">
        <div className="flex items-center gap-1.5">
          {isKilled ? (
            <Skull className="h-3.5 w-3.5 text-gray-400" />
          ) : isInstant ? (
            <Skull className="h-3.5 w-3.5 text-red-600" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5 text-yellow-600" />
          )}
          <SeverityBadge trigger={trigger} />
        </div>
      </td>

      {/* Email */}
      <td className="py-2 px-3 max-w-[200px]">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="font-medium text-sm truncate block">
                {trigger.inboxEmail}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <p>{trigger.inboxEmail}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </td>

      {/* Domain */}
      <td className="py-2 px-3 w-[140px]">
        <span className="text-sm text-muted-foreground truncate block">
          {trigger.domainName}
        </span>
      </td>

      {/* Trigger Type + Value */}
      <td className="py-2 px-3 w-[180px]">
        <div className="text-sm">
          <span className="font-medium">{threshold.label}</span>
          <span className="text-muted-foreground ml-1.5">
            {formatValue(trigger.value, trigger.threshold)}
          </span>
        </div>
      </td>

      {/* Detected */}
      <td className="py-2 px-3 w-[70px]">
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatTimeAgo(trigger.detectedAt)}
        </span>
      </td>

      {/* Actions */}
      <td className="py-2 px-3 w-[160px]">
        {isPending && (
          <div className="flex items-center gap-1.5">
            {isInstant ? (
              <>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => onExecute?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-7 text-xs px-2"
                >
                  <Skull className="h-3 w-3 mr-1" />
                  {isExecuting ? 'Killing...' : 'Execute'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDismiss?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-7 px-1.5 text-muted-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => onExecute?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-7 text-xs px-2"
                >
                  Kill
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onRetest?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-7 text-xs px-2"
                >
                  Retest
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDismiss?.(trigger.id)}
                  disabled={isExecuting}
                  className="h-7 px-1.5 text-muted-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        )}
        {isKilled && trigger.resolvedAt && (
          <span className="text-xs text-muted-foreground">
            Killed {formatTimeAgo(trigger.resolvedAt)} ago
          </span>
        )}
      </td>
    </tr>
  );
}

export function KillTriggerTable({
  triggers,
  onExecute,
  onDismiss,
  onRetest,
  executingTriggerIds = [],
}: KillTriggerTableProps) {
  if (triggers.length === 0) {
    return null;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b bg-muted/50">
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Status
            </th>
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Email
            </th>
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Domain
            </th>
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Trigger
            </th>
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Time
            </th>
            <th className="py-2 px-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Action
            </th>
          </tr>
        </thead>
        <tbody>
          {triggers.map((trigger) => (
            <TriggerRow
              key={trigger.id}
              trigger={trigger}
              onExecute={onExecute}
              onDismiss={onDismiss}
              onRetest={onRetest}
              isExecuting={executingTriggerIds.includes(trigger.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
