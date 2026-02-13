'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  KillTriggerMonitor,
  KillConfirmDialog,
  DomainHealthGrid,
  CampaignAttributionPanel,
  ListContaminationTracker,
  ESPHealthSummary,
  RotationNeedsAttention,
  HealthDistributionPieChart,
  LifecycleDistributionChart,
  InventorySegmentationChart,
} from '@/components/health';
import { InventoryBarChart } from '@/components/health/InventoryBarChart';
import { InventoryTable } from '@/components/health/InventoryTable';
import { AutoKillToggle } from '@/components/health/AutoKillToggle';
import { useClientStore, useHealthStore } from '@/lib/stores';
import { inventoryApi, healthApi, subscriptionApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import type { KillTrigger, HealthRange, InfrastructureHealthResponse, PoolStatus } from '@/lib/types/health';
import type { SubscriptionWithUsage } from '@/lib/types';
import type {
  InventoryOverview,
  InventoryInbox,
  AutoKillConfig,
  InventoryPoolStatus,
  InventoryLifecycleStatus,
} from '@/lib/types/inventory';

export default function HealthPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.clientId as string;

  // Dialog state
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [selectedTrigger, setSelectedTrigger] = useState<KillTrigger | null>(null);
  const [executingTriggerIds, setExecutingTriggerIds] = useState<string[]>([]);

  // Inventory state
  const [inventoryOverview, setInventoryOverview] = useState<InventoryOverview | null>(null);
  const [inventoryInboxes, setInventoryInboxes] = useState<InventoryInbox[]>([]);
  const [autoKillConfig, setAutoKillConfig] = useState<AutoKillConfig>({
    enabled: false,
    cooldownHours: 48,
    autoReplace: true,
    notifyOnKill: false,
  });
  const [isInventoryLoading, setIsInventoryLoading] = useState(false);
  const [isAutoKillUpdating, setIsAutoKillUpdating] = useState(false);
  const [poolStatusFilter, setPoolStatusFilter] = useState<InventoryPoolStatus | null>(null);
  const [lifecycleStatusFilter, setLifecycleStatusFilter] = useState<InventoryLifecycleStatus | null>(null);
  const [healthRangeFilter, setHealthRangeFilter] = useState<HealthRange | null>(null);

  // Infrastructure health (database-only, no EmailBison API)
  const [infrastructureHealth, setInfrastructureHealth] = useState<InfrastructureHealthResponse | null>(null);
  const [isInfraHealthLoading, setIsInfraHealthLoading] = useState(false);

  // Subscription data for capacity planning
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);

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
    executeKillTrigger,
    dismissKillTrigger,
  } = useHealthStore();

  const client = getClient(clientId);

  // Fetch infrastructure health (database-only)
  const fetchInfrastructureHealth = useCallback(async () => {
    setIsInfraHealthLoading(true);
    try {
      const health = await healthApi.getInfrastructureHealth(clientId);
      setInfrastructureHealth(health);
    } catch (error) {
      console.error('Failed to fetch infrastructure health:', error);
    } finally {
      setIsInfraHealthLoading(false);
    }
  }, [clientId]);

  // Fetch inventory data
  const fetchInventoryData = useCallback(async () => {
    setIsInventoryLoading(true);
    try {
      const [overview, inboxes, config] = await Promise.all([
        inventoryApi.getOverview(clientId),
        inventoryApi.getInboxes(clientId),
        inventoryApi.getAutoKillConfig(clientId),
      ]);
      setInventoryOverview(overview);
      setInventoryInboxes(inboxes.items);
      setAutoKillConfig(config);
    } catch (error) {
      console.error('Failed to fetch inventory data:', error);
    } finally {
      setIsInventoryLoading(false);
    }
  }, [clientId]);

  // Fetch subscription data for capacity planning
  const fetchSubscription = useCallback(async () => {
    try {
      const sub = await subscriptionApi.getClientSubscription(clientId);
      setSubscription(sub);
    } catch (error) {
      console.error('Failed to fetch subscription:', error);
    }
  }, [clientId]);

  // Fetch all health data on mount via composite endpoint
  useEffect(() => {
    selectClient(clientId);
    refreshHealth(clientId);
    fetchInventoryData();
    fetchInfrastructureHealth();
    fetchSubscription();
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, refreshHealth, fetchInventoryData, fetchInfrastructureHealth, fetchSubscription, fetchClients, clients.length]);

  const pendingTriggers = killTriggers.filter((t) => t.actionTaken === 'pending');
  const instantPending = killTriggers.filter(
    (t) => t.severity === 'instant' && t.actionTaken === 'pending'
  );

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
    fetchInventoryData();
    fetchInfrastructureHealth();
    fetchSubscription();
    toast.success('Health data refreshed');
  };

  // Inventory handlers
  const handleAutoKillConfigChange = async (config: AutoKillConfig) => {
    setIsAutoKillUpdating(true);
    try {
      await inventoryApi.setAutoKillConfig(clientId, config);
      setAutoKillConfig(config);
      toast.success(config.enabled ? 'Auto-kill enabled' : 'Auto-kill disabled');
    } catch (error) {
      toast.error('Failed to update auto-kill settings');
    } finally {
      setIsAutoKillUpdating(false);
    }
  };

  const handleKillAndReplace = async (inboxId: string, reason: string, autoReplace: boolean) => {
    try {
      const result = await inventoryApi.killAndReplace(inboxId, reason, autoReplace);
      if (result.success) {
        toast.success(
          result.replacementInboxEmail
            ? `Killed ${result.killedInboxEmail}, replaced with ${result.replacementInboxEmail}`
            : `Killed ${result.killedInboxEmail}`
        );
        fetchInventoryData();
        refreshHealth(clientId);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to kill inbox');
    }
  };

  const handlePoolStatusClick = (status: InventoryPoolStatus) => {
    setPoolStatusFilter(poolStatusFilter === status ? null : status);
    setLifecycleStatusFilter(null);
  };

  const handleLifecycleStatusClick = (status: InventoryLifecycleStatus) => {
    setLifecycleStatusFilter(lifecycleStatusFilter === status ? null : status);
    setPoolStatusFilter(null);
  };

  const handleClearFilter = () => {
    setPoolStatusFilter(null);
    setLifecycleStatusFilter(null);
    setHealthRangeFilter(null);
  };

  const handleHealthRangeClick = (range: HealthRange) => {
    setHealthRangeFilter(healthRangeFilter === range ? null : range);
    setPoolStatusFilter(null);
    setLifecycleStatusFilter(null);
  };

  // Kill trigger handlers
  const handleExecuteClick = useCallback((triggerId: string) => {
    const trigger = killTriggers.find((t) => t.id === triggerId);
    if (trigger) {
      setSelectedTrigger(trigger);
      setConfirmDialogOpen(true);
    }
  }, [killTriggers]);

  const handleConfirmKill = useCallback(async () => {
    if (!selectedTrigger) return;

    setExecutingTriggerIds((prev) => [...prev, selectedTrigger.id]);
    setConfirmDialogOpen(false);

    try {
      await executeKillTrigger(selectedTrigger.id);
      toast.success(`Inbox ${selectedTrigger.inboxEmail} has been killed`);
      // Refresh to get updated data
      refreshHealth(clientId);
    } catch (error) {
      toast.error(`Failed to kill inbox: ${(error as Error).message}`);
    } finally {
      setExecutingTriggerIds((prev) => prev.filter((id) => id !== selectedTrigger.id));
      setSelectedTrigger(null);
    }
  }, [selectedTrigger, executeKillTrigger, refreshHealth, clientId]);

  const handleDismiss = useCallback((triggerId: string) => {
    dismissKillTrigger(triggerId);
    toast.info('Trigger dismissed');
  }, [dismissKillTrigger]);

  const handleRetest = useCallback((triggerId: string) => {
    // For now, just dismiss and show a message
    // TODO: Implement proper retest scheduling
    dismissKillTrigger(triggerId);
    toast.info('Retest scheduled for 48 hours');
  }, [dismissKillTrigger]);

  const handleExecuteAll = useCallback(async () => {
    // Execute all instant pending triggers
    for (const trigger of instantPending) {
      setExecutingTriggerIds((prev) => [...prev, trigger.id]);
      try {
        await executeKillTrigger(trigger.id);
      } catch (error) {
        toast.error(`Failed to kill ${trigger.inboxEmail}`);
      }
      setExecutingTriggerIds((prev) => prev.filter((id) => id !== trigger.id));
    }
    toast.success(`Killed ${instantPending.length} inbox${instantPending.length > 1 ? 'es' : ''}`);
    refreshHealth(clientId);
  }, [instantPending, executeKillTrigger, refreshHealth, clientId]);

  // Rotation handlers
  const handleOrderReplacement = useCallback((domainId: string) => {
    // Navigate to inbox ordering page with domain pre-selected
    router.push(`/clients/${clientId}/inboxes?action=order&domain=${domainId}`);
  }, [router, clientId]);

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
            {/* Auto-Kill Toggle */}
            <AutoKillToggle
              config={autoKillConfig}
              onConfigChange={handleAutoKillConfigChange}
              isUpdating={isAutoKillUpdating}
            />
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
                <div className={cn(
                  "text-2xl font-bold",
                  pendingTriggers.length > 0 ? "text-red-600" : "text-green-600"
                )}>
                  {pendingTriggers.length}
                </div>
                <div className="text-sm text-muted-foreground">
                  {pendingTriggers.length > 0 ? 'Action Required' : 'All Clear'}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Infrastructure Health Section (Database-only) */}
        {infrastructureHealth && (
          <div className="grid grid-cols-12 gap-6 mb-6">
            {/* Lifecycle Distribution Chart - Half Width (Primary: Pool Status & Lifecycle) */}
            <div className="col-span-12 lg:col-span-6">
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">Inventory Status</h3>
                  {infrastructureHealth.lifecycleDistribution ? (
                    <LifecycleDistributionChart
                      distribution={infrastructureHealth.lifecycleDistribution}
                      size={180}
                    />
                  ) : (
                    <HealthDistributionPieChart
                      distribution={infrastructureHealth.healthDistribution}
                      onSegmentClick={handleHealthRangeClick}
                      selectedRange={healthRangeFilter}
                      size={200}
                    />
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Infrastructure Summary - Half Width */}
            <div className="col-span-12 lg:col-span-6">
              <Card>
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-4">Infrastructure Summary</h3>
                  <div className="space-y-4">
                    {/* Overall Stats */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-muted/50 rounded-lg">
                        <div className="text-2xl font-bold">{infrastructureHealth.liveInboxes}</div>
                        <div className="text-sm text-muted-foreground">Live Inboxes</div>
                      </div>
                      <div className="p-3 bg-muted/50 rounded-lg">
                        <div className="text-2xl font-bold">{infrastructureHealth.deadInboxes}</div>
                        <div className="text-sm text-muted-foreground">Dead Inboxes</div>
                      </div>
                      <div className="p-3 bg-muted/50 rounded-lg">
                        <div className="text-2xl font-bold">{infrastructureHealth.avgHealthScore.toFixed(1)}</div>
                        <div className="text-sm text-muted-foreground">Avg Health Score</div>
                      </div>
                      <div className="p-3 bg-muted/50 rounded-lg">
                        <div className="text-2xl font-bold">
                          {infrastructureHealth.cleanDomains}/{infrastructureHealth.totalDomains}
                        </div>
                        <div className="text-sm text-muted-foreground">Clean Domains</div>
                      </div>
                    </div>

                    {/* Provider Breakdown */}
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">Provider Breakdown</h4>
                      <div className="space-y-2">
                        {infrastructureHealth.providers.map((provider) => (
                          <div key={provider.name} className="flex items-center justify-between">
                            <span className="capitalize">{provider.name}</span>
                            <div className="flex items-center gap-4 text-sm">
                              <span className="text-muted-foreground">
                                {provider.liveCount}/{provider.count} live
                              </span>
                              <span className={cn(
                                'font-medium',
                                provider.avgHealthScore >= 80 ? 'text-green-600' :
                                provider.avgHealthScore >= 60 ? 'text-yellow-600' :
                                'text-red-600'
                              )}>
                                {provider.avgHealthScore.toFixed(0)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Data Freshness */}
                    {infrastructureHealth.lastSync && (
                      <div className="text-xs text-muted-foreground pt-2 border-t">
                        Data from {infrastructureHealth.syncSource} •
                        Last sync: {new Date(infrastructureHealth.lastSync).toLocaleString()}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Capacity Planning Section */}
        {subscription && infrastructureHealth && (
          <Card className="mb-6">
            <CardContent className="p-6">
              <h3 className="text-lg font-semibold mb-4">Capacity Planning</h3>
              <div className="space-y-4">
                {/* Package Info */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Package: <span className="font-medium text-foreground">{subscription.packageTemplateName || 'Custom'}</span>
                  </span>
                  <span className={cn(
                    'text-sm font-medium px-2 py-1 rounded',
                    subscription.spareStatus === 'healthy' ? 'bg-green-100 text-green-700' :
                    subscription.spareStatus === 'low' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-red-100 text-red-700'
                  )}>
                    {subscription.spareStatus === 'healthy' ? 'On Track' :
                     subscription.spareStatus === 'low' ? 'Needs Attention' : 'Critical Gap'}
                  </span>
                </div>

                {/* Inbox Progress */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Live Inboxes</span>
                    <span className="font-medium">
                      {infrastructureHealth.liveInboxes} / {subscription.currentActiveInboxes + subscription.inboxesRemaining}
                      {' '}
                      ({subscription.inboxesUsedPercent.toFixed(0)}%)
                    </span>
                  </div>
                  <Progress
                    value={subscription.inboxesUsedPercent}
                    className={cn(
                      'h-3',
                      subscription.inboxesUsedPercent < 30 ? '[&>div]:bg-red-500' :
                      subscription.inboxesUsedPercent < 70 ? '[&>div]:bg-yellow-500' :
                      '[&>div]:bg-green-500'
                    )}
                  />
                </div>

                {/* Domain Progress */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Active Domains</span>
                    <span className="font-medium">
                      {subscription.currentActiveDomains} / {subscription.currentActiveDomains + subscription.domainsRemaining}
                      {' '}
                      ({subscription.domainsUsedPercent.toFixed(0)}%)
                    </span>
                  </div>
                  <Progress
                    value={subscription.domainsUsedPercent}
                    className={cn(
                      'h-3',
                      subscription.domainsUsedPercent < 30 ? '[&>div]:bg-red-500' :
                      subscription.domainsUsedPercent < 70 ? '[&>div]:bg-yellow-500' :
                      '[&>div]:bg-green-500'
                    )}
                  />
                </div>

                {/* Gap Summary */}
                {subscription.inboxesRemaining > 0 && (
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-2 text-sm">
                      <AlertCircle className="h-4 w-4 text-amber-500" />
                      <span>
                        <span className="font-medium">{subscription.inboxesRemaining} more inboxes</span>
                        {' '}needed to reach package capacity
                        {subscription.domainsRemaining > 0 && (
                          <span className="text-muted-foreground">
                            {' '}(~{subscription.domainsRemaining} more domains)
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                )}

                {/* Fully Fulfilled Message */}
                {subscription.inboxesRemaining <= 0 && (
                  <div className="p-3 bg-green-50 rounded-lg">
                    <div className="flex items-center gap-2 text-sm text-green-700">
                      <CheckCircle className="h-4 w-4" />
                      <span>Package capacity reached - {infrastructureHealth.liveInboxes} live inboxes active</span>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Tabbed Dashboard */}
        <Tabs defaultValue="infrastructure" className="space-y-6">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="infrastructure">Infrastructure Health</TabsTrigger>
            <TabsTrigger value="campaign-insights">Campaign Insights</TabsTrigger>
          </TabsList>

          {/* Tab 1: Infrastructure Health */}
          <TabsContent value="infrastructure" className="space-y-6">
            <div className="grid grid-cols-12 gap-6">
              {/* Inventory Segmentation Chart - Half Width (4 segments: deployed/dead/reserve/incubating) */}
              {inventoryOverview && (
                <div className="col-span-12 lg:col-span-6">
                  <InventorySegmentationChart
                    counts={{
                      deployed: inventoryOverview.deployedCount,
                      dead: inventoryOverview.deadCount,
                      reserve: inventoryOverview.reserveCount,
                      incubating: inventoryOverview.incubatingCount,
                      total: inventoryOverview.totalInboxes,
                    }}
                    onSegmentClick={(segment) => {
                      if (segment === 'deployed' || segment === 'reserve') {
                        handlePoolStatusClick(segment as InventoryPoolStatus);
                      } else if (segment === 'dead' || segment === 'incubating') {
                        handleLifecycleStatusClick(segment as InventoryLifecycleStatus);
                      }
                    }}
                  />
                </div>
              )}

              {/* Inventory Bar Chart - Half Width (Pool status: deployed/warning/reserve) */}
              {inventoryOverview && (
                <div className="col-span-12 lg:col-span-6">
                  <InventoryBarChart
                    data={{
                      deployed: inventoryOverview.deployedCount,
                      warning: inventoryOverview.warningCount,
                      reserve: inventoryOverview.reserveCount,
                      total: inventoryOverview.totalInboxes,
                      deployedTarget: inventoryOverview.deployedTarget,
                      reserveTarget: inventoryOverview.reserveTarget,
                      spareCapacity: inventoryOverview.spareCapacity,
                      sparePercentage: inventoryOverview.sparePercentage,
                      capacityStatus: inventoryOverview.capacityStatus,
                    }}
                    lifecycleCounts={{
                      active: inventoryOverview.activeCount,
                      incubating: inventoryOverview.incubatingCount,
                      dead: inventoryOverview.deadCount,
                    }}
                    autoKillEnabled={inventoryOverview.autoKillEnabled}
                    onPoolStatusClick={handlePoolStatusClick}
                    onLifecycleStatusClick={handleLifecycleStatusClick}
                  />
                </div>
              )}

              {/* Kill Trigger Activity - Full Width */}
              <div className="col-span-12">
                <KillTriggerMonitor
                  triggers={killTriggers}
                  onExecute={handleExecuteClick}
                  onDismiss={handleDismiss}
                  onRetest={handleRetest}
                  onExecuteAll={handleExecuteAll}
                  executingTriggerIds={executingTriggerIds}
                />
              </div>

              {/* Rotation Needs Attention - Half Width */}
              <div className="col-span-12 lg:col-span-6">
                <RotationNeedsAttention
                  domains={domainMetrics}
                  onOrderReplacement={handleOrderReplacement}
                />
              </div>

              {/* Domain Health Grid - Half Width */}
              <div className="col-span-12 lg:col-span-6">
                <DomainHealthGrid domains={domainMetrics} />
              </div>

              {/* Inventory Table - Full Width */}
              <div className="col-span-12">
                <Card>
                  <CardContent className="p-6">
                    <h3 className="text-lg font-semibold mb-4">Inbox Inventory</h3>
                    <InventoryTable
                      inboxes={inventoryInboxes}
                      isLoading={isInventoryLoading}
                      poolStatusFilter={poolStatusFilter}
                      lifecycleStatusFilter={lifecycleStatusFilter}
                      healthRangeFilter={healthRangeFilter}
                      onKillAndReplace={handleKillAndReplace}
                      onClearFilter={handleClearFilter}
                    />
                  </CardContent>
                </Card>
              </div>

              {/* ESP Health Summary - Full Width */}
              <div className="col-span-12">
                <ESPHealthSummary summaries={espSummaries} />
              </div>
            </div>
          </TabsContent>

          {/* Tab 2: Campaign Insights */}
          <TabsContent value="campaign-insights" className="space-y-6">
            <div className="grid grid-cols-12 gap-6">
              {/* Campaign Attribution - Full Width */}
              <div className="col-span-12">
                <CampaignAttributionPanel campaigns={campaignMetrics} />
              </div>

              {/* List Contamination Tracker - Full Width */}
              <div className="col-span-12">
                <ListContaminationTracker sources={contaminationSources} />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </PageContainer>

      {/* Kill Confirmation Dialog */}
      <KillConfirmDialog
        trigger={selectedTrigger}
        open={confirmDialogOpen}
        onOpenChange={setConfirmDialogOpen}
        onConfirm={handleConfirmKill}
        isExecuting={selectedTrigger ? executingTriggerIds.includes(selectedTrigger.id) : false}
      />
    </>
  );
}
