'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Loader2, AlertCircle, Workflow, Package, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { PackageFulfillmentDashboard } from '@/components/purchasing';
import { ProcurementTab, InventoryTab, JobsTab } from '@/components/inboxes/tabs';
import { useInboxPageState } from '@/lib/hooks';

export default function InboxesPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  // Use centralized state hook
  const {
    client,
    isLoadingClients,
    clientDomains,
    domainsByStatus,
    providerBreakdown,
    clientInboxes,
    isLoading,
    error,
    loadingDomainIds,
    subscription,
    canGenerateInfo,
    refreshDomains,
    refreshInboxes,
    refreshAll,
    handleExpandDomain,
  } = useInboxPageState(clientId);

  // Tab state - default based on inventory
  const [activeTab, setActiveTab] = useState<string>('inventory');
  const [hasSetDefaultTab, setHasSetDefaultTab] = useState(false);

  // Set default tab based on inventory once data loads
  useEffect(() => {
    if (!hasSetDefaultTab && !isLoading && clientDomains.length >= 0) {
      setActiveTab(domainsByStatus.inventory.length === 0 ? 'procurement' : 'inventory');
      setHasSetDefaultTab(true);
    }
  }, [isLoading, domainsByStatus.inventory.length, clientDomains.length, hasSetDefaultTab]);

  // Loading state
  if ((isLoading || isLoadingClients) && clientDomains.length === 0 && clientInboxes.length === 0) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  // Error state
  if (error && clientDomains.length === 0 && clientInboxes.length === 0) {
    return (
      <PageContainer>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center gap-2">
            Failed to load infrastructure: {error}
            <Button variant="link" size="sm" onClick={refreshAll}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </PageContainer>
    );
  }

  // Client not found
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
    <TooltipProvider>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Package Fulfillment Dashboard - always visible above tabs */}
        <PackageFulfillmentDashboard
          subscription={subscription}
          inventoryDomainsCount={domainsByStatus.inventory.length}
          purchasedNeedingSetupCount={domainsByStatus.purchased.length}
          pendingDomainsCount={domainsByStatus.pendingCount}
          approvedDomainsCount={domainsByStatus.approvedCount}
          totalInboxesCount={clientInboxes.length}
          entraDomainsActive={providerBreakdown.entra}
          googleDomainsActive={providerBreakdown.google}
          onNavigateToTab={setActiveTab}
        />

        {/* Tab Navigation - 3 tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="procurement" className="flex items-center gap-2">
              <Workflow className="h-4 w-4" />
              Procurement
            </TabsTrigger>
            <TabsTrigger value="inventory" className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Active Inventory
            </TabsTrigger>
            <TabsTrigger value="jobs" className="flex items-center gap-2">
              <History className="h-4 w-4" />
              Jobs
            </TabsTrigger>
          </TabsList>

          {/* Procurement Tab */}
          <TabsContent value="procurement">
            <ProcurementTab
              clientId={clientId}
              clientName={client.name}
              subscription={subscription}
              canGenerateInfo={canGenerateInfo}
              candidateDomains={domainsByStatus.candidates}
              purchasedDomains={domainsByStatus.purchased}
              pendingCount={domainsByStatus.pendingCount}
              approvedCount={domainsByStatus.approvedCount}
              onRefreshDomains={refreshDomains}
              onRefreshInboxes={refreshInboxes}
            />
          </TabsContent>

          {/* Active Inventory Tab */}
          <TabsContent value="inventory">
            <InventoryTab
              clientId={clientId}
              inventoryDomains={domainsByStatus.inventory}
              approvedDomains={domainsByStatus.approved}
              allDomains={clientDomains}
              allInboxes={clientInboxes}
              loadingDomainIds={loadingDomainIds}
              onExpandDomain={handleExpandDomain}
            />
          </TabsContent>

          {/* Jobs Tab */}
          <TabsContent value="jobs">
            <JobsTab
              clientId={clientId}
              onJobRetried={refreshDomains}
            />
          </TabsContent>
        </Tabs>
      </PageContainer>
    </TooltipProvider>
  );
}
