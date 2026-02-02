'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import {
  KillTriggerMonitor,
  BackupCapacityGauge,
  DomainHealthGrid,
  CampaignAttributionPanel,
  ListContaminationTracker,
  ESPHealthSummary,
} from '@/components/health';
import { useClientStore, useHealthStore } from '@/lib/stores';
import { cn } from '@/lib/utils';

export default function HealthPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const isLoadingClients = useClientStore((state) => state.isLoading);

  const {
    overallSummary,
    killTriggers,
    backupCapacity,
    domainMetrics,
    campaignMetrics,
    contaminationSources,
    espSummaries,
    isLoading,
    error,
    refreshHealth,
    lastRefresh,
  } = useHealthStore();

  const client = getClient(clientId);

  // Fetch all health data on mount via composite endpoint
  useEffect(() => {
    selectClient(clientId);
    refreshHealth(clientId);
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, refreshHealth, fetchClients, clients.length]);

  const pendingTriggers = killTriggers.filter((t) => t.actionTaken === 'pending');

  // Status indicator
  const statusConfig = {
    healthy: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100', label: 'Healthy' },
    warning: { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-100', label: 'Warning' },
    critical: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100', label: 'Critical' },
  };

  const currentStatus = statusConfig[overallSummary?.status || 'healthy'];
  const StatusIcon = currentStatus.icon;

  const handleRefresh = () => {
    refreshHealth(clientId);
    toast.success('Health data refreshed');
  };

  // Loading state
  if ((isLoading || isLoadingClients) && !overallSummary) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  // Error state
  if (error && !overallSummary) {
    return (
      <PageContainer>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center gap-2">
            Failed to load health data: {error}
            <Button variant="link" size="sm" onClick={handleRefresh}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </PageContainer>
    );
  }

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Client not found</p>
        </div>
      </PageContainer>
    );
  }

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Status Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className={cn('flex items-center gap-2 px-4 py-2 rounded-lg', currentStatus.bg)}>
              <StatusIcon className={cn('h-5 w-5', currentStatus.color)} />
              <span className={cn('font-semibold', currentStatus.color)}>
                {currentStatus.label}
              </span>
            </div>
            {overallSummary && (
              <span className="text-sm text-muted-foreground">
                {overallSummary.statusMessage}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {lastRefresh && (
              <span className="text-sm text-muted-foreground">
                Last refresh: {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
              <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Overview Stats */}
        {overallSummary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="p-4">
                <div className="text-2xl font-bold">{overallSummary.healthScore}</div>
                <div className="text-sm text-muted-foreground">Health Score</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-2xl font-bold">
                  {overallSummary.liveDomains}/{overallSummary.totalDomains}
                </div>
                <div className="text-sm text-muted-foreground">Live Domains</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-2xl font-bold">
                  {overallSummary.liveInboxes}/{overallSummary.totalInboxes}
                </div>
                <div className="text-sm text-muted-foreground">Live Inboxes</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-yellow-600">
                  {pendingTriggers.length}
                </div>
                <div className="text-sm text-muted-foreground">Active Monitors</div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Main Dashboard Grid */}
        <div className="grid grid-cols-12 gap-6">
          {/* Kill Trigger Activity - Left Column */}
          <div className="col-span-12 lg:col-span-6">
            <KillTriggerMonitor triggers={killTriggers} />
          </div>

          {/* Backup Capacity - Right Column */}
          <div className="col-span-12 lg:col-span-6">
            <BackupCapacityGauge capacity={backupCapacity} />
          </div>

          {/* Domain Health Grid - Full Width */}
          <div className="col-span-12">
            <DomainHealthGrid domains={domainMetrics} />
          </div>

          {/* Campaign Attribution - Half Width */}
          <div className="col-span-12 lg:col-span-6">
            <CampaignAttributionPanel campaigns={campaignMetrics} />
          </div>

          {/* List Contamination - Half Width */}
          <div className="col-span-12 lg:col-span-6">
            <ListContaminationTracker sources={contaminationSources} />
          </div>

          {/* ESP Health Summary - Full Width */}
          <div className="col-span-12">
            <ESPHealthSummary summaries={espSummaries} />
          </div>
        </div>
      </PageContainer>
    </>
  );
}
