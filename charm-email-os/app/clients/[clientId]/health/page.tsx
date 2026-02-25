'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Loader2, AlertCircle, Globe, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  KillConfirmDialog,
  CampaignAttributionPanel,
  ListContaminationTracker,
  InventorySegmentationChart,
  KPICard,
  ESPComparisonCard,
  KillVelocityChart,
  KillBreakdownChart,
  DisconnectedInboxesList,
  SendingCapacityChart,
} from '@/components/health';
import { DomainInboxTree, InboxForm } from '@/components/inboxes';
import { useClientStore, useHealthStore, useInfrastructureStore } from '@/lib/stores';
import { inventoryApi, healthApi, subscriptionApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import type { KillTrigger, InfrastructureHealthResponse, KillBreakdownResponse, DailyVolumeHistoryResponse } from '@/lib/types/health';
import type { SubscriptionWithUsage } from '@/lib/types';
import type { InventoryOverview } from '@/lib/types/inventory';

// Kill velocity data type
interface KillVelocityData {
  weekly: Array<{ week: string; deaths: number }>;
  totalDeaths7d: number;
  totalDeaths30d: number;
  churnRate7d: number;
  trend: 'up' | 'down' | 'stable';
}

export default function HealthPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.clientId as string;

  // Dialog state
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [selectedTrigger, setSelectedTrigger] = useState<KillTrigger | null>(null);
  const [executingTriggerIds, setExecutingTriggerIds] = useState<string[]>([]);

  // Inventory state for charts
  const [inventoryOverview, setInventoryOverview] = useState<InventoryOverview | null>(null);

  // Infrastructure health (database-only, no EmailBison API)
  const [infrastructureHealth, setInfrastructureHealth] = useState<InfrastructureHealthResponse | null>(null);
  const [isInfraHealthLoading, setIsInfraHealthLoading] = useState(false);

  // Kill velocity data for trend chart
  const [killVelocity, setKillVelocity] = useState<KillVelocityData | null>(null);

  // Kill breakdown data (why inboxes died)
  const [killBreakdown, setKillBreakdown] = useState<KillBreakdownResponse | null>(null);

  // Daily volume history for sending capacity chart
  const [dailyVolume, setDailyVolume] = useState<DailyVolumeHistoryResponse | null>(null);

  // Subscription data for capacity planning
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);

  // Inbox form state
  const [showInboxForm, setShowInboxForm] = useState(false);

  // Client store
  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const isLoadingClients = useClientStore((state) => state.isLoading);

  // Infrastructure store for domains/inboxes (for DomainInboxTree)
  const allDomains = useInfrastructureStore((state) => state.domains);
  const allStoreInboxes = useInfrastructureStore((state) => state.inboxes);
  const loadingDomainIds = useInfrastructureStore((state) => state.loadingDomainIds);
  const fetchDomainsByClient = useInfrastructureStore((state) => state.fetchDomainsByClient);
  const fetchInboxesForDomainLazy = useInfrastructureStore((state) => state.fetchInboxesForDomainLazy);

  // Health store
  const {
    overallSummary,
    killTriggers,
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

  // Filter domains/inboxes for this client
  const clientDomains = useMemo(
    () => allDomains.filter((d) => d.clientId === clientId),
    [allDomains, clientId]
  );

  const clientInboxes = useMemo(
    () => allStoreInboxes.filter((i) => i.clientId === clientId),
    [allStoreInboxes, clientId]
  );

  // Inventory domains (active, legacy, warming, flagged, dead)
  const inventoryDomains = useMemo(
    () => clientDomains.filter((d) =>
      ['active', 'legacy', 'warming', 'flagged', 'dead'].includes(d.status)
    ),
    [clientDomains]
  );

  // Approved domains (for adding inboxes)
  const approvedDomains = useMemo(
    () => clientDomains.filter((d) =>
      ['purchased', 'active', 'warming'].includes(d.status)
    ),
    [clientDomains]
  );

  // Handle domain expand for lazy loading
  const handleExpandDomain = useCallback(
    (domainId: string) => {
      fetchInboxesForDomainLazy(domainId, clientId);
    },
    [fetchInboxesForDomainLazy, clientId]
  );

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

  // Fetch inventory overview
  const fetchInventoryData = useCallback(async () => {
    try {
      const overview = await inventoryApi.getOverview(clientId);
      setInventoryOverview(overview);
    } catch (error) {
      console.error('Failed to fetch inventory data:', error);
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

  // Fetch kill velocity data
  const fetchKillVelocity = useCallback(async () => {
    try {
      const velocity = await healthApi.getKillVelocity(clientId);
      setKillVelocity(velocity);
    } catch (error) {
      console.error('Failed to fetch kill velocity:', error);
    }
  }, [clientId]);

  // Fetch kill breakdown data (why inboxes died)
  const fetchKillBreakdown = useCallback(async () => {
    try {
      const breakdown = await healthApi.getKillBreakdown(clientId);
      setKillBreakdown(breakdown);
    } catch (error) {
      console.error('Failed to fetch kill breakdown:', error);
    }
  }, [clientId]);

  // Fetch daily volume history for sending capacity chart
  const fetchDailyVolume = useCallback(async () => {
    try {
      const volume = await healthApi.getDailyVolumeHistory(clientId, { days: 90 });
      setDailyVolume(volume);
    } catch (error) {
      console.error('Failed to fetch daily volume history:', error);
    }
  }, [clientId]);

  // Fetch all data on mount
  useEffect(() => {
    selectClient(clientId);
    refreshHealth(clientId);
    fetchInventoryData();
    fetchInfrastructureHealth();
    fetchSubscription();
    fetchKillVelocity();
    fetchKillBreakdown();
    fetchDailyVolume();
    fetchDomainsByClient(clientId);
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, refreshHealth, fetchInventoryData, fetchInfrastructureHealth, fetchSubscription, fetchKillVelocity, fetchKillBreakdown, fetchDailyVolume, fetchDomainsByClient, fetchClients, clients.length]);

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

  const handleRefresh = () => {
    refreshHealth(clientId);
    fetchInventoryData();
    fetchInfrastructureHealth();
    fetchSubscription();
    fetchKillVelocity();
    fetchKillBreakdown();
    fetchDailyVolume();
    fetchDomainsByClient(clientId);
    toast.success('Health data refreshed');
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
      refreshHealth(clientId);
    } catch (error) {
      toast.error(`Failed to kill inbox: ${(error as Error).message}`);
    } finally {
      setExecutingTriggerIds((prev) => prev.filter((id) => id !== selectedTrigger.id));
      setSelectedTrigger(null);
    }
  }, [selectedTrigger, executeKillTrigger, refreshHealth, clientId]);

  // Calculate KPI values
  const totalInboxes = (subscription?.currentActiveInboxes ?? 0) + (subscription?.inboxesRemaining ?? 0) || infrastructureHealth?.totalInboxes || 0;
  const liveInboxes = infrastructureHealth?.liveInboxes || 0;
  const inboxUtilization = totalInboxes > 0 ? (liveInboxes / totalInboxes * 100) : 0;

  const totalDomains = (subscription?.currentActiveDomains ?? 0) + (subscription?.domainsRemaining ?? 0) || infrastructureHealth?.totalDomains || 0;
  const liveDomains = subscription?.currentActiveDomains || infrastructureHealth?.cleanDomains || 0;
  const domainCoverage = totalDomains > 0 ? (liveDomains / totalDomains * 100) : 0;

  // ESP summaries for comparison card
  const gmailSummary = espSummaries?.find(s => s.provider.toLowerCase() === 'gmail');
  const microsoftSummary = espSummaries?.find(s => s.provider.toLowerCase().includes('microsoft') || s.provider.toLowerCase().includes('outlook'));

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
        {/* Status Header - Simplified */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold">Health Dashboard</h1>
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

        {/* Hero Section: 4 KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KPICard
            value={overallSummary?.healthScore || 0}
            label="Health Score"
            status={overallSummary?.status === 'healthy' ? 'healthy' : overallSummary?.status === 'warning' ? 'warning' : 'critical'}
            subtext={currentStatus.label}
          />
          <KPICard
            value={`${liveInboxes}/${totalInboxes}`}
            label="Inbox Utilization"
            subtext={`${inboxUtilization.toFixed(1)}%`}
            status={inboxUtilization >= 70 ? 'healthy' : inboxUtilization >= 40 ? 'warning' : 'critical'}
          />
          <KPICard
            value={`${liveDomains}/${totalDomains}`}
            label="Domain Coverage"
            subtext={`${domainCoverage.toFixed(1)}%`}
            status={domainCoverage >= 70 ? 'healthy' : domainCoverage >= 40 ? 'warning' : 'critical'}
          />
          <KPICard
            value={killVelocity ? `${killVelocity.churnRate7d.toFixed(1)}%` : '—'}
            label="Weekly Churn"
            subtext={killVelocity ? `${killVelocity.totalDeaths7d} deaths` : 'No data'}
            trend={killVelocity?.trend || 'stable'}
            status={
              killVelocity?.churnRate7d && killVelocity.churnRate7d > 5 ? 'critical' :
              killVelocity?.churnRate7d && killVelocity.churnRate7d > 2 ? 'warning' : 'healthy'
            }
          />
        </div>

        {/* Tabs - Now at TOP after KPI cards */}
        <Tabs defaultValue="dashboard" className="space-y-6">
          <TabsList className="grid w-full max-w-lg grid-cols-3">
            <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
            <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
            <TabsTrigger value="campaign-insights">Campaign Insights</TabsTrigger>
          </TabsList>

          {/* Tab 1: Dashboard - Charts Grid */}
          <TabsContent value="dashboard" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Capacity Planning */}
              {subscription && infrastructureHealth && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg font-semibold">Capacity Planning</CardTitle>
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
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Package Info */}
                    <div className="text-sm text-muted-foreground">
                      Package: <span className="font-medium text-foreground">{subscription.packageTemplateName || 'Custom'}</span>
                    </div>

                    {/* Inbox Progress */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Live Inboxes</span>
                        <span className="font-medium">
                          {infrastructureHealth.liveInboxes} / {totalInboxes}
                          {' '}({inboxUtilization.toFixed(0)}%)
                        </span>
                      </div>
                      <Progress
                        value={inboxUtilization}
                        className={cn(
                          'h-3',
                          inboxUtilization < 30 ? '[&>div]:bg-red-500' :
                          inboxUtilization < 70 ? '[&>div]:bg-yellow-500' :
                          '[&>div]:bg-green-500'
                        )}
                      />
                    </div>

                    {/* Domain Progress */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Active Domains</span>
                        <span className="font-medium">
                          {liveDomains} / {totalDomains}
                          {' '}({domainCoverage.toFixed(0)}%)
                        </span>
                      </div>
                      <Progress
                        value={domainCoverage}
                        className={cn(
                          'h-3',
                          domainCoverage < 30 ? '[&>div]:bg-red-500' :
                          domainCoverage < 70 ? '[&>div]:bg-yellow-500' :
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
                          </span>
                        </div>
                      </div>
                    )}

                    {subscription.inboxesRemaining <= 0 && (
                      <div className="p-3 bg-green-50 rounded-lg">
                        <div className="flex items-center gap-2 text-sm text-green-700">
                          <CheckCircle className="h-4 w-4" />
                          <span>Package capacity reached</span>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Inbox Distribution (4 segments) */}
              {inventoryOverview && (
                <InventorySegmentationChart
                  counts={{
                    deployed: inventoryOverview.deployedCount,
                    dead: inventoryOverview.deadCount,
                    reserve: inventoryOverview.reserveCount,
                    incubating: inventoryOverview.incubatingCount,
                    total: inventoryOverview.totalInboxes,
                    killedByTrigger: inventoryOverview.killedByTrigger,
                    deactivated: inventoryOverview.deactivated,
                  }}
                />
              )}

              {/* Kill Velocity Chart */}
              {killVelocity && (
                <KillVelocityChart weeklyData={killVelocity.weekly} />
              )}

              {/* Kill Breakdown Chart - Why inboxes died */}
              <KillBreakdownChart breakdown={killBreakdown} />

              {/* Sending Capacity Over Time */}
              {dailyVolume && dailyVolume.daysReturned > 0 && (
                <SendingCapacityChart
                  snapshots={dailyVolume.snapshots}
                  killEvents={dailyVolume.killEvents}
                  totalEmailsSent={dailyVolume.totalEmailsSent}
                  avgDailyCapacity={dailyVolume.avgDailyCapacity}
                  avgUtilizationPct={dailyVolume.avgUtilizationPct}
                  totalKills={dailyVolume.totalKills}
                />
              )}

              {/* ESP Performance Comparison */}
              <ESPComparisonCard
                gmail={gmailSummary ? {
                  provider: 'Gmail',
                  activeInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase() === 'gmail')?.liveCount || 0,
                  totalInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase() === 'gmail')?.count || 0,
                  deadInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase() === 'gmail')?.deadCount || 0,
                  killedByTrigger: killBreakdown?.byProvider?.gmail || 0,
                  avgHealthScore: infrastructureHealth?.providers?.find(p => p.name.toLowerCase() === 'gmail')?.avgHealthScore,
                  inboxPlacement: gmailSummary.inboxPlacementRate,
                  spamPlacement: gmailSummary.spamPlacementRate,
                  reputation: gmailSummary.reputation as 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN',
                } : infrastructureHealth?.providers?.find(p => p.name.toLowerCase() === 'gmail') ? {
                  provider: 'Gmail',
                  activeInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase() === 'gmail')?.liveCount || 0,
                  totalInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase() === 'gmail')?.count || 0,
                  deadInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase() === 'gmail')?.deadCount || 0,
                  killedByTrigger: killBreakdown?.byProvider?.gmail || 0,
                  avgHealthScore: infrastructureHealth.providers.find(p => p.name.toLowerCase() === 'gmail')?.avgHealthScore,
                } : undefined}
                microsoft={microsoftSummary ? {
                  provider: 'Microsoft',
                  activeInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.liveCount || 0,
                  totalInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.count || 0,
                  deadInboxes: infrastructureHealth?.providers?.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.deadCount || 0,
                  killedByTrigger: killBreakdown?.byProvider?.microsoft || 0,
                  avgHealthScore: infrastructureHealth?.providers?.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.avgHealthScore,
                  inboxPlacement: microsoftSummary.inboxPlacementRate,
                  spamPlacement: microsoftSummary.spamPlacementRate,
                  reputation: microsoftSummary.reputation as 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN',
                } : infrastructureHealth?.providers?.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook')) ? {
                  provider: 'Microsoft',
                  activeInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.liveCount || 0,
                  totalInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.count || 0,
                  deadInboxes: infrastructureHealth.providers.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.deadCount || 0,
                  killedByTrigger: killBreakdown?.byProvider?.microsoft || 0,
                  avgHealthScore: infrastructureHealth.providers.find(p => p.name.toLowerCase().includes('microsoft') || p.name.toLowerCase().includes('outlook'))?.avgHealthScore,
                } : undefined}
              />
            </div>
          </TabsContent>

          {/* Tab 2: Infrastructure - Domains & Inboxes Tree */}
          <TabsContent value="infrastructure" className="space-y-6">
            {/* Disconnected Inboxes Alert */}
            <DisconnectedInboxesList clientId={clientId} />

            <Card>
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <Globe className="h-4 w-4" />
                      Domains & Inboxes
                    </CardTitle>
                    <CardDescription className="mt-1">
                      Click a domain to expand and see its inboxes
                    </CardDescription>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setShowInboxForm(true)}
                      disabled={approvedDomains.length === 0}
                    >
                      <Plus className="h-4 w-4 mr-1" />
                      Add Inbox
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {inventoryDomains.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <Globe className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="font-medium">No active domains</p>
                    <p className="text-sm mt-1">Go to the Infrastructure page to generate and purchase domains.</p>
                  </div>
                ) : (
                  <DomainInboxTree
                    domains={inventoryDomains}
                    inboxes={clientInboxes}
                    onExpandDomain={handleExpandDomain}
                    loadingDomainIds={loadingDomainIds}
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 3: Campaign Insights */}
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

      {/* Inbox Form */}
      <InboxForm
        clientId={clientId}
        open={showInboxForm}
        onOpenChange={setShowInboxForm}
      />

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
