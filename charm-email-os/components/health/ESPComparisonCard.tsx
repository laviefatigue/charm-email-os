'use client';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { Mail, Shield, Database, Clock } from 'lucide-react';

interface ESPMetrics {
  provider: string;
  activeInboxes: number;  // Live inboxes
  totalInboxes: number;   // All inboxes (live + dead)
  deadInboxes?: number;   // Dead inboxes (total)
  killedByTrigger?: number;  // System-killed (health metric) - NEW
  avgHealthScore?: number; // Average health score for this ESP
  inboxPlacement?: number; // From external API (Google Postmaster / SNDS)
  spamPlacement?: number;  // From external API
  reputation?: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
}

interface ESPComparisonCardProps {
  gmail?: ESPMetrics;
  microsoft?: ESPMetrics;
  dataSource?: 'database' | 'external';
  className?: string;
}

const REPUTATION_CONFIG = {
  HIGH: { bg: 'bg-green-100', text: 'text-green-700', label: 'High' },
  MEDIUM: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Medium' },
  LOW: { bg: 'bg-red-100', text: 'text-red-700', label: 'Low' },
  UNKNOWN: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Unknown' },
};

function ESPColumn({ metrics, providerName, icon }: {
  metrics?: ESPMetrics;
  providerName: string;
  icon: React.ReactNode;
}) {
  if (!metrics) {
    return (
      <div className="flex-1 p-4 text-center">
        <div className="flex items-center justify-center gap-2 mb-3">
          {icon}
          <span className="font-semibold text-muted-foreground">{providerName}</span>
        </div>
        <p className="text-sm text-muted-foreground">No data</p>
      </div>
    );
  }

  const hasExternalData = metrics.inboxPlacement !== undefined && metrics.inboxPlacement > 0;
  const rawReputation = metrics.reputation?.toUpperCase() || 'UNKNOWN';
  const reputation = (rawReputation in REPUTATION_CONFIG ? rawReputation : 'UNKNOWN') as keyof typeof REPUTATION_CONFIG;
  const repConfig = REPUTATION_CONFIG[reputation];

  // Calculate death breakdown from local data
  const deadCount = metrics.deadInboxes ?? (metrics.totalInboxes - metrics.activeInboxes);
  const killedByTrigger = metrics.killedByTrigger ?? 0;

  // Kill rate = system kills / (live + system kills) - excludes business churn
  const killRateBase = metrics.activeInboxes + killedByTrigger;
  const killRate = killRateBase > 0
    ? ((killedByTrigger / killRateBase) * 100)
    : 0;

  // Derive reputation from health score if no external data
  const derivedReputation = !hasExternalData && metrics.avgHealthScore !== undefined
    ? (metrics.avgHealthScore >= 80 ? 'HIGH' :
       metrics.avgHealthScore >= 60 ? 'MEDIUM' : 'LOW') as keyof typeof REPUTATION_CONFIG
    : reputation;
  const finalRepConfig = hasExternalData ? repConfig : REPUTATION_CONFIG[derivedReputation];

  return (
    <div className="flex-1 p-4">
      {/* Provider Header */}
      <div className="flex items-center justify-center gap-2 mb-4">
        {icon}
        <span className="font-semibold">{providerName}</span>
      </div>

      {/* Main Metric - Health Score or Placement */}
      <div className="text-center mb-4">
        {hasExternalData ? (
          <>
            <div className="text-3xl font-bold text-foreground">
              {Math.round(metrics.inboxPlacement!)}%
            </div>
            <div className="text-xs text-muted-foreground">Inbox Placement</div>
          </>
        ) : (
          <>
            <div className="text-3xl font-bold text-foreground">
              {metrics.avgHealthScore !== undefined ? Math.round(metrics.avgHealthScore) : '—'}
            </div>
            <div className="text-xs text-muted-foreground">Avg Health Score</div>
          </>
        )}
      </div>

      {/* Progress Bar */}
      <div className="h-2 bg-muted rounded-full overflow-hidden mb-4">
        <div
          className={cn(
            'h-full rounded-full transition-all',
            hasExternalData
              ? (metrics.inboxPlacement! >= 95 ? 'bg-green-500' :
                 metrics.inboxPlacement! >= 80 ? 'bg-amber-500' : 'bg-red-500')
              : ((metrics.avgHealthScore ?? 0) >= 80 ? 'bg-green-500' :
                 (metrics.avgHealthScore ?? 0) >= 60 ? 'bg-amber-500' : 'bg-red-500')
          )}
          style={{
            width: `${Math.min(hasExternalData ? metrics.inboxPlacement! : (metrics.avgHealthScore ?? 0), 100)}%`
          }}
        />
      </div>

      {/* Stats Row */}
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Live Inboxes</span>
          <span className="font-medium text-green-600">{metrics.activeInboxes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Dead</span>
          <span className="font-medium text-gray-500">
            {killedByTrigger > 0 ? (
              <span title={`${killedByTrigger} killed by triggers, ${deadCount - killedByTrigger} deactivated`}>
                {deadCount} ({killedByTrigger} killed)
              </span>
            ) : (
              deadCount
            )}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Kill Rate</span>
          <span className={cn(
            'font-medium',
            killRate > 15 ? 'text-red-600' :
            killRate > 5 ? 'text-amber-600' :
            'text-green-600'
          )}>
            {killRate.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Reputation Badge or Data Pending */}
      <div className="mt-4 flex justify-center">
        {hasExternalData ? (
          <Badge variant="outline" className={cn('gap-1', finalRepConfig.bg, finalRepConfig.text)}>
            <Shield className="w-3 h-3" />
            {finalRepConfig.label} Reputation
          </Badge>
        ) : (
          <Badge variant="outline" className={cn('gap-1', finalRepConfig.bg, finalRepConfig.text)}>
            <Database className="w-3 h-3" />
            Local Data
          </Badge>
        )}
      </div>
    </div>
  );
}

export function ESPComparisonCard({ gmail, microsoft, dataSource = 'database', className }: ESPComparisonCardProps) {
  const hasExternalData = (gmail?.inboxPlacement ?? 0) > 0 || (microsoft?.inboxPlacement ?? 0) > 0;

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">ESP Performance</CardTitle>
          {!hasExternalData && (
            <Badge variant="outline" className="text-xs gap-1">
              <Clock className="w-3 h-3" />
              Postmaster Data Pending
            </Badge>
          )}
        </div>
        {!hasExternalData && (
          <CardDescription className="text-xs mt-1">
            Inbox placement data from Google Postmaster Tools and Microsoft SNDS not yet integrated.
            Showing local health metrics.
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex divide-x">
          <ESPColumn
            metrics={gmail}
            providerName="Gmail"
            icon={
              <div className="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center">
                <Mail className="w-3 h-3 text-red-600" />
              </div>
            }
          />
          <ESPColumn
            metrics={microsoft}
            providerName="Microsoft"
            icon={
              <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center">
                <Mail className="w-3 h-3 text-blue-600" />
              </div>
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}
