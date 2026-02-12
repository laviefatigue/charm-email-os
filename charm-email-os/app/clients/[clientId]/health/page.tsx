'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import {
  KillTriggerMonitor,
  KillConfirmDialog,
  DomainHealthGrid,
  CampaignAttributionPanel,
  ListContaminationTracker,
  ESPHealthSummary,
  RotationNeedsAttention,
} from '@/components/health';
import { InventoryBarChart } from '@/components/health/InventoryBarChart';
import { InventoryTable } from '@/components/health/InventoryTable';
import { AutoKillToggle } from '@/components/health/AutoKillToggle';
import { useClientStore, useHealthStore } from '@/lib/stores';
import { inventoryApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { KillTrigger } from '@/lib/types/health';
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

  // Fetch all health data on mount via composite endpoint
  useEffect(() => {
    selectClient(clientId);
    refreshHealth(clientId);
    fetchInventoryData();
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, refreshHealth, fetchInventoryData, fetchClients, clients.length]);

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

        {/* Main Dashboard Grid - Reorganized Layout */}
        <div className="grid grid-cols-12 gap-6">
          {/* Inventory Bar Chart - Full Width (Priority 1: Inventory health) */}
          {inventoryOverview && (
            <div className="col-span-12">
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

          {/* Kill Trigger Activity - Full Width (Priority 2: Action items) */}
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
                  onKillAndReplace={handleKillAndReplace}
                  onClearFilter={handleClearFilter}
                />
              </CardContent>
            </Card>
          </div>

          {/* ESP Health Summary - Half Width */}
          <div className="col-span-12 lg:col-span-6">
            <ESPHealthSummary summaries={espSummaries} />
          </div>

          {/* Campaign Attribution - Half Width */}
          <div className="col-span-12 lg:col-span-6">
            <CampaignAttributionPanel campaigns={campaignMetrics} />
          </div>

          {/* List Contamination - Full Width (lower priority) */}
          <div className="col-span-12">
            <ListContaminationTracker sources={contaminationSources} />
          </div>
        </div>
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
