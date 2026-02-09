'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Inbox, Server, Activity, AlertTriangle, Cloud, Mail, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { InventoryHealth, InventoryAttentionItem } from '@/lib/types';

interface InventoryHealthDashboardProps {
  health?: InventoryHealth | null;
  isLoading?: boolean;
  onRefresh?: () => void;
  pendingInboxes?: number;
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'blue',
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof Inbox;
  color?: 'blue' | 'green' | 'orange' | 'red' | 'gray';
}) {
  const colorStyles = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    orange: 'bg-orange-50 text-orange-600',
    red: 'bg-red-50 text-red-600',
    gray: 'bg-gray-50 text-gray-600',
  };

  return (
    <div className="bg-white rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <div className={cn('p-2 rounded-lg', colorStyles[color])}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-muted-foreground truncate">{title}</p>
          {subtitle && (
            <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ProviderCard({
  name,
  count,
  connected,
  connectionRate,
  avgHealth,
}: {
  name: string;
  count: number;
  connected: number;
  connectionRate: number;
  avgHealth: number;
}) {
  const isMicrosoft = name.toLowerCase().includes('microsoft') || name.toLowerCase().includes('entra');
  const Icon = isMicrosoft ? Cloud : Mail;
  const iconColor = isMicrosoft ? 'text-blue-500' : 'text-red-500';

  // Determine health color
  const healthColor = avgHealth >= 80 ? 'text-green-600' : avgHealth >= 60 ? 'text-yellow-600' : 'text-red-600';
  const connectionColor = connectionRate >= 80 ? 'text-green-600' : connectionRate >= 50 ? 'text-yellow-600' : 'text-red-600';

  return (
    <div className="bg-white rounded-lg border p-3">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={cn('h-4 w-4', iconColor)} />
        <span className="font-medium text-sm">{name}</span>
      </div>
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Inboxes:</span>
          <span className="font-medium">{count}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Connected:</span>
          <span className={cn('font-medium', connectionColor)}>
            {connected} ({connectionRate.toFixed(0)}%)
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Avg Health:</span>
          <span className={cn('font-medium', healthColor)}>{avgHealth.toFixed(0)}</span>
        </div>
      </div>
    </div>
  );
}

function AttentionItem({ item }: { item: InventoryAttentionItem }) {
  const isCritical = item.severity === 'critical';

  if (item.type === 'blacklist') {
    return (
      <div className={cn(
        'flex items-start gap-2 p-2 rounded text-sm',
        isCritical ? 'bg-red-50' : 'bg-yellow-50'
      )}>
        <AlertTriangle className={cn('h-4 w-4 mt-0.5 shrink-0', isCritical ? 'text-red-500' : 'text-yellow-500')} />
        <div>
          <span className="font-medium">{item.domain}</span>
          <span className="text-muted-foreground"> listed on </span>
          <span className="font-medium">
            {item.lists?.slice(0, 3).join(', ')}
            {item.lists && item.lists.length > 3 ? ` (+${item.lists.length - 3} more)` : ''}
          </span>
        </div>
      </div>
    );
  }

  if (item.type === 'high_bounce') {
    return (
      <div className={cn(
        'flex items-start gap-2 p-2 rounded text-sm',
        isCritical ? 'bg-red-50' : 'bg-orange-50'
      )}>
        <Mail className={cn('h-4 w-4 mt-0.5 shrink-0', isCritical ? 'text-red-500' : 'text-orange-500')} />
        <div>
          <span className="font-medium font-mono text-xs">{item.email}</span>
          <span className="text-muted-foreground"> - </span>
          <span className={cn('font-medium', isCritical ? 'text-red-600' : 'text-orange-600')}>
            {((item.bounceRate ?? 0) * 100).toFixed(1)}% bounce rate
          </span>
          {item.bounced && item.sent && (
            <span className="text-muted-foreground text-xs"> ({item.bounced}/{item.sent} sent)</span>
          )}
        </div>
      </div>
    );
  }

  if (item.type === 'low_health') {
    return (
      <div className="flex items-start gap-2 p-2 rounded bg-yellow-50 text-sm">
        <Activity className="h-4 w-4 mt-0.5 shrink-0 text-yellow-500" />
        <div>
          <span className="font-medium font-mono text-xs">{item.email}</span>
          <span className="text-muted-foreground"> - </span>
          <span className="font-medium text-yellow-600">Health: {item.healthScore}</span>
        </div>
      </div>
    );
  }

  return null;
}

export function InventoryHealthDashboard({ health, isLoading, onRefresh, pendingInboxes = 0 }: InventoryHealthDashboardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Loading inventory health from EmailBison...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!health) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="text-center text-muted-foreground">
            No inventory health data available
          </div>
        </CardContent>
      </Card>
    );
  }

  const healthPercent = health.totalInboxes > 0
    ? Math.round((health.connectedInboxes / health.totalInboxes) * 100)
    : 0;

  const hasAttentionItems = health.attentionItems && health.attentionItems.length > 0;
  const criticalCount = health.attentionItems?.filter(i => i.severity === 'critical').length ?? 0;
  const warningCount = health.attentionItems?.filter(i => i.severity === 'warning').length ?? 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Server className="h-5 w-5 text-muted-foreground" />
            Infrastructure Health
          </CardTitle>
          <div className="flex items-center gap-3">
            {pendingInboxes > 0 && (
              <span className="text-xs text-yellow-700 bg-yellow-50 px-2 py-0.5 rounded-full flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                {pendingInboxes} pending approval
              </span>
            )}
            {health.emailbisonAvailable ? (
              <span className="text-xs text-green-600 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-green-500"></span>
                EmailBison: Live
              </span>
            ) : (
              <span className="text-xs text-yellow-600 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-yellow-500"></span>
                {health.emailbisonError || 'EmailBison: Unavailable'}
              </span>
            )}
            {onRefresh && (
              <button
                onClick={onRefresh}
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="Refresh"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            title="Total Inboxes"
            value={health.totalInboxes}
            icon={Inbox}
            color="blue"
          />
          <StatCard
            title="Connected"
            value={health.connectedInboxes}
            subtitle={`${health.connectionRate.toFixed(0)}% connection rate`}
            icon={Activity}
            color={health.connectionRate >= 80 ? 'green' : health.connectionRate >= 50 ? 'orange' : 'red'}
          />
          <StatCard
            title="Domains"
            value={health.totalDomains}
            subtitle={health.flaggedDomains > 0 ? `${health.flaggedDomains} flagged` : 'All clean'}
            icon={Server}
            color={health.flaggedDomains > 0 ? 'orange' : 'green'}
          />
          <StatCard
            title="Health Score"
            value={`${health.avgHealthScore.toFixed(0)}`}
            subtitle="Average across inboxes"
            icon={Activity}
            color={health.avgHealthScore >= 80 ? 'green' : health.avgHealthScore >= 60 ? 'orange' : 'red'}
          />
        </div>

        {/* Provider breakdown */}
        {health.providers && health.providers.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-2">Provider Breakdown</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {health.providers.map((provider) => (
                <ProviderCard
                  key={provider.name}
                  name={provider.name}
                  count={provider.count}
                  connected={provider.connected}
                  connectionRate={provider.connectionRate}
                  avgHealth={provider.avgHealth}
                />
              ))}
            </div>
          </div>
        )}

        {/* Attention items */}
        {hasAttentionItems && (
          <div>
            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Needs Attention
              {criticalCount > 0 && (
                <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                  {criticalCount} critical
                </span>
              )}
              {warningCount > 0 && (
                <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">
                  {warningCount} warning
                </span>
              )}
            </h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {health.attentionItems.slice(0, 10).map((item, index) => (
                <AttentionItem key={index} item={item} />
              ))}
              {health.attentionItems.length > 10 && (
                <p className="text-xs text-muted-foreground text-center py-1">
                  +{health.attentionItems.length - 10} more items
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
