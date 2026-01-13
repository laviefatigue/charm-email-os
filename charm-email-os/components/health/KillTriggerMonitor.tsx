'use client';

import { Activity, CheckCircle, Skull, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { KillTriggerCard } from './KillTriggerCard';
import type { KillTrigger } from '@/lib/types/health';

interface KillTriggerMonitorProps {
  triggers: KillTrigger[];
}

export function KillTriggerMonitor({ triggers }: KillTriggerMonitorProps) {
  // Separate by status
  const recentKills = triggers.filter((t) => t.actionTaken === 'killed');
  const confirmingTriggers = triggers.filter(
    (t) => t.severity === 'confirming' && t.actionTaken === 'pending'
  );
  const instantPending = triggers.filter(
    (t) => t.severity === 'instant' && t.actionTaken === 'pending'
  );

  const hasActivity = triggers.length > 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Kill Trigger Activity
          </CardTitle>
          <div className="flex items-center gap-3 text-sm">
            {recentKills.length > 0 && (
              <span className="flex items-center gap-1 text-gray-600">
                <Skull className="h-4 w-4" />
                {recentKills.length} killed
              </span>
            )}
            {confirmingTriggers.length > 0 && (
              <span className="flex items-center gap-1 text-yellow-600">
                <AlertCircle className="h-4 w-4" />
                {confirmingTriggers.length} monitoring
              </span>
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
          <div className="space-y-6">
            {/* Instant kills waiting to execute */}
            {instantPending.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Skull className="h-4 w-4 text-red-600" />
                  <h4 className="font-semibold text-red-700">Executing Instant Kill</h4>
                  <span className="text-xs text-muted-foreground">
                    Auto-killing now
                  </span>
                </div>
                <div className="space-y-3">
                  {instantPending.map((trigger) => (
                    <KillTriggerCard key={trigger.id} trigger={trigger} />
                  ))}
                </div>
              </div>
            )}

            {/* Confirming triggers being monitored */}
            {confirmingTriggers.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <AlertCircle className="h-4 w-4 text-yellow-600" />
                  <h4 className="font-semibold text-yellow-700">Monitoring</h4>
                  <span className="text-xs text-muted-foreground">
                    Auto-retest in 48h
                  </span>
                </div>
                <div className="space-y-3">
                  {confirmingTriggers.map((trigger) => (
                    <KillTriggerCard key={trigger.id} trigger={trigger} />
                  ))}
                </div>
              </div>
            )}

            {/* Recent kills */}
            {recentKills.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Skull className="h-4 w-4 text-gray-500" />
                  <h4 className="font-semibold text-gray-600">Recent Kills</h4>
                </div>
                <div className="space-y-3">
                  {recentKills.map((trigger) => (
                    <KillTriggerCard key={trigger.id} trigger={trigger} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
