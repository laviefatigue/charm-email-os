'use client';

import { useState } from 'react';
import { Activity, CheckCircle, Skull, AlertCircle, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { KillTriggerTable } from './KillTriggerTable';
import type { KillTrigger } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface KillTriggerMonitorProps {
  triggers: KillTrigger[];
  onExecute?: (triggerId: string) => void;
  onDismiss?: (triggerId: string) => void;
  onRetest?: (triggerId: string) => void;
  onExecuteAll?: () => void;
  executingTriggerIds?: string[];
}

interface CollapsibleSectionProps {
  title: string;
  count: number;
  icon: React.ReactNode;
  iconColor: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function CollapsibleSection({
  title,
  count,
  icon,
  iconColor,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/30 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <span className={iconColor}>{icon}</span>
          <span className="font-medium text-sm">{title}</span>
          <span className={cn(
            "text-xs px-1.5 py-0.5 rounded-full",
            count > 0 ? "bg-gray-200 text-gray-700" : "bg-gray-100 text-gray-500"
          )}>
            {count}
          </span>
        </div>
      </button>
      {isOpen && (
        <div className="border-t">
          {children}
        </div>
      )}
    </div>
  );
}

export function KillTriggerMonitor({
  triggers,
  onExecute,
  onDismiss,
  onRetest,
  onExecuteAll,
  executingTriggerIds = [],
}: KillTriggerMonitorProps) {
  // Separate by status
  const recentKills = triggers.filter((t) => t.actionTaken === 'killed');
  const confirmingTriggers = triggers.filter(
    (t) => t.severity === 'confirming' && t.actionTaken === 'pending'
  );
  const instantPending = triggers.filter(
    (t) => t.severity === 'instant' && t.actionTaken === 'pending'
  );

  const hasActivity = triggers.length > 0;
  const hasPendingActions = instantPending.length > 0 || confirmingTriggers.length > 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Kill Trigger Activity
          </CardTitle>
          <div className="flex items-center gap-3">
            {/* Summary badges */}
            <div className="flex items-center gap-2 text-sm">
              {instantPending.length > 0 && (
                <span className="flex items-center gap-1 text-red-600">
                  <Skull className="h-4 w-4" />
                  {instantPending.length} critical
                </span>
              )}
              {confirmingTriggers.length > 0 && (
                <span className="flex items-center gap-1 text-yellow-600">
                  <AlertCircle className="h-4 w-4" />
                  {confirmingTriggers.length} reviewing
                </span>
              )}
              {recentKills.length > 0 && (
                <span className="flex items-center gap-1 text-gray-500">
                  <Skull className="h-4 w-4" />
                  {recentKills.length} flagged
                </span>
              )}
            </div>
            {/* Bulk action */}
            {onExecuteAll && instantPending.length > 1 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={onExecuteAll}
                disabled={executingTriggerIds.length > 0}
              >
                <Skull className="h-3.5 w-3.5 mr-1.5" />
                Execute All ({instantPending.length})
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!hasActivity ? (
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle className="h-10 w-10 mx-auto mb-3 text-green-500" />
            <p className="font-medium">All Clear</p>
            <p className="text-sm mt-1">No kill trigger activity</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Action Required - Instant kills */}
            {instantPending.length > 0 && (
              <CollapsibleSection
                title="Action Required"
                count={instantPending.length}
                icon={<AlertTriangle className="h-4 w-4" />}
                iconColor="text-red-600"
                defaultOpen={true}
              >
                <KillTriggerTable
                  triggers={instantPending}
                  onExecute={onExecute}
                  onDismiss={onDismiss}
                  onRetest={onRetest}
                  executingTriggerIds={executingTriggerIds}
                />
              </CollapsibleSection>
            )}

            {/* Under Review - Confirming triggers */}
            {confirmingTriggers.length > 0 && (
              <CollapsibleSection
                title="Under Review"
                count={confirmingTriggers.length}
                icon={<AlertCircle className="h-4 w-4" />}
                iconColor="text-yellow-600"
                defaultOpen={true}
              >
                <KillTriggerTable
                  triggers={confirmingTriggers}
                  onExecute={onExecute}
                  onDismiss={onDismiss}
                  onRetest={onRetest}
                  executingTriggerIds={executingTriggerIds}
                />
              </CollapsibleSection>
            )}

            {/* Recently Flagged - Collapsed by default */}
            {recentKills.length > 0 && (
              <CollapsibleSection
                title="Recently Flagged"
                count={recentKills.length}
                icon={<Skull className="h-4 w-4" />}
                iconColor="text-gray-500"
                defaultOpen={false}
              >
                <KillTriggerTable
                  triggers={recentKills}
                  executingTriggerIds={executingTriggerIds}
                />
              </CollapsibleSection>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
