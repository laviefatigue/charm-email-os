'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Plus, Globe, Mail, Info, Sparkles, AlertTriangle, CheckCheck, Loader2, AlertCircle, ShoppingCart, Package, History, Server, Workflow } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { EmptyState } from '@/components/shared';
import {
  DomainCard,
  InboxCard,
  DomainForm,
  InboxForm,
  DomainEditModal,
  InboxEditModal,
  DomainInboxTree,
} from '@/components/inboxes';
import { DomainCandidatesTable, DomainsNeedingSetupTable, InboxProvisionModal, PurchaseJobsTable, PackageFulfillmentDashboard } from '@/components/purchasing';
import { useClientStore, useInfrastructureStore } from '@/lib/stores';
import { domainSourcingApi, subscriptionApi, type CanGenerateResponse, type GenerateForClientResponse } from '@/lib/api';
import type { Domain, Inbox, SubscriptionWithUsage } from '@/lib/types';

export default function InboxesPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const isLoadingClients = useClientStore((state) => state.isLoading);

  // Subscribe to the actual arrays in the store for reactivity
  const allDomains = useInfrastructureStore((state) => state.domains);
  const allStoreInboxes = useInfrastructureStore((state) => state.inboxes);
  const isLoading = useInfrastructureStore((state) => state.isLoading);
  const error = useInfrastructureStore((state) => state.error);
  const loadingDomainIds = useInfrastructureStore((state) => state.loadingDomainIds);
  const fetchDomainsByClient = useInfrastructureStore((state) => state.fetchDomainsByClient);
  const fetchInboxesByClient = useInfrastructureStore((state) => state.fetchInboxesByClient);
  const fetchInboxesForDomainLazy = useInfrastructureStore((state) => state.fetchInboxesForDomainLazy);
  const generateDomainsFromOnboarding = useInfrastructureStore((state) => state.generateDomainsFromOnboarding);
  const generateInboxesFromOnboarding = useInfrastructureStore((state) => state.generateInboxesFromOnboarding);
  const approveDomain = useInfrastructureStore((state) => state.approveDomain);
  const approveInbox = useInfrastructureStore((state) => state.approveInbox);

  const client = getClient(clientId);

  // Fetch data on mount - domains only, inboxes are lazy loaded on expand
  useEffect(() => {
    selectClient(clientId);
    fetchDomainsByClient(clientId);
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchDomainsByClient, fetchClients, clients.length]);

  // Filter domains/inboxes for this client - now reactive because we subscribe to the arrays
  const domains = useMemo(() => allDomains.filter((d) => d.clientId === clientId), [allDomains, clientId]);

  // Inventory domains: Domains with inboxes in EmailBison (active, legacy, warming, flagged, dead)
  // 'legacy' = pre-existing domains before new workflow (1/22/26) - managed but needs audit
  const inventoryDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'active' || d.status === 'legacy' || d.status === 'warming' || d.status === 'flagged' || d.status === 'dead')
  ), [allDomains, clientId]);

  // Purchase domains: pending, approved, rejected, purchased (need inbox setup), provisioning
  const purchaseDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'pending' || d.status === 'pending_approval' || d.status === 'approved' || d.status === 'rejected' || d.status === 'purchased' || d.status === 'provisioning')
  ), [allDomains, clientId]);

  // Purchased domains needing inbox setup (bought but no inboxes yet)
  const purchasedNeedingSetup = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'purchased' || d.status === 'provisioning')
  ), [allDomains, clientId]);

  // Approved domains ready for inbox creation (purchased or active)
  const approvedDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'purchased' || d.status === 'active' || d.status === 'warming')
  ), [allDomains, clientId]);

  const allInboxes = useMemo(() => allStoreInboxes.filter((i) => i.clientId === clientId), [allStoreInboxes, clientId]);

  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);
  const [showDomainForm, setShowDomainForm] = useState(false);
  const [showInboxForm, setShowInboxForm] = useState(false);
  const [editingDomain, setEditingDomain] = useState<Domain | null>(null);
  const [editingInbox, setEditingInbox] = useState<Inbox | null>(null);
  const [showInboxPurchaseWizard, setShowInboxPurchaseWizard] = useState(false);
  const [selectedDomainsForSetup, setSelectedDomainsForSetup] = useState<string[]>([]);
  const [hasAgeOverride, setHasAgeOverride] = useState(false);
  const [canGenerateInfo, setCanGenerateInfo] = useState<CanGenerateResponse | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);

  // Default tab: new clients (no inventory) → procurement, existing → inventory
  const [activeTab, setActiveTab] = useState<string>(() => {
    return 'inventory'; // Will be updated once data loads
  });
  const [hasSetDefaultTab, setHasSetDefaultTab] = useState(false);

  // Set default tab based on inventory once data loads
  useEffect(() => {
    if (!hasSetDefaultTab && !isLoading && domains.length >= 0) {
      setActiveTab(inventoryDomains.length === 0 ? 'procurement' : 'inventory');
      setHasSetDefaultTab(true);
    }
  }, [isLoading, inventoryDomains.length, domains.length, hasSetDefaultTab]);

  // Fetch can-generate info for the client
  useEffect(() => {
    const fetchCanGenerate = async () => {
      try {
        const info = await domainSourcingApi.canGenerate(clientId);
        setCanGenerateInfo(info);
      } catch (error) {
        console.error('Failed to fetch can-generate info:', error);
      }
    };
    fetchCanGenerate();
  }, [clientId]);

  // Fetch subscription for the client
  useEffect(() => {
    const fetchSubscription = async () => {
      try {
        const sub = await subscriptionApi.getClientSubscription(clientId);
        setSubscription(sub);
      } catch (error) {
        console.error('Failed to fetch subscription:', error);
      }
    };
    fetchSubscription();
  }, [clientId]);

  const filteredInboxes = useMemo(() => {
    if (!selectedDomainId) return allInboxes;
    return allInboxes.filter((i) => i.domainId === selectedDomainId);
  }, [selectedDomainId, allInboxes]);

  // Wrapper to pass clientId to lazy load function
  const handleExpandDomain = useCallback((domainId: string) => {
    fetchInboxesForDomainLazy(domainId, clientId);
  }, [fetchInboxesForDomainLazy, clientId]);

  // Count pending approvals (use both 'pending' and legacy 'pending_approval')
  const pendingDomainsCount = domains.filter((d) => d.status === 'pending' || d.status === 'pending_approval').length;
  const approvedDomainsCount = domains.filter((d) => d.status === 'approved').length;
  const pendingInboxes = allInboxes.filter((i) => i.status === 'pending_approval').length;

  // Provider breakdown from inventory domains
  const entraDomainsActive = inventoryDomains.filter((d) => d.infrastructureType === 'entra').length;
  const googleDomainsActive = inventoryDomains.filter((d) => d.infrastructureType === 'google').length;

  // Loading state
  if ((isLoading || isLoadingClients) && domains.length === 0 && allInboxes.length === 0) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  // Error state
  if (error && domains.length === 0 && allInboxes.length === 0) {
    return (
      <PageContainer>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center gap-2">
            Failed to load infrastructure: {error}
            <Button variant="link" size="sm" onClick={() => {
              fetchDomainsByClient(clientId);
              fetchInboxesByClient(clientId);
            }}>
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

  const handleGenerateDomains = async () => {
    if (!client.onboardingData) {
      toast.error('Please complete onboarding first');
      return;
    }
    const generated = await generateDomainsFromOnboarding(clientId, client.onboardingData);
    toast.success(`Generated ${generated.length} domain suggestions`);
  };

  // Direct inline domain generation - queues job for containerized Claude Code worker
  const handleGenerateDomainsInline = async () => {
    if (!canGenerateInfo?.canGenerate) {
      toast.error(canGenerateInfo?.message || 'Cannot generate domains');
      return;
    }
    setIsGenerating(true);
    try {
      // Create a job for the Claude Code domain worker
      const job = await domainSourcingApi.createGenerationJob(clientId, 10);
      toast.success(`Domain generation job queued. Domains will appear shortly.`);

      // Poll for job completion and refresh domains
      const pollInterval = setInterval(async () => {
        try {
          const status = await domainSourcingApi.getJobStatus(job.jobId);
          if (status.status === 'completed') {
            clearInterval(pollInterval);
            await fetchDomainsByClient(clientId);
            // Auto-trigger bulk price check for newly generated domains
            try {
              toast.success('Domain generation complete! Checking prices...');
              await domainSourcingApi.checkPricesBulk({ clientId });
              await fetchDomainsByClient(clientId); // Refresh with prices
              toast.success('Prices checked across registrars.');
            } catch {
              toast.success('Domain generation complete! Price check can be done manually.');
            }
            setIsGenerating(false);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            toast.error(status.errorMessage || 'Domain generation failed');
            setIsGenerating(false);
          }
        } catch {
          // Ignore polling errors
        }
      }, 3000); // Poll every 3 seconds

      // Timeout after 2 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (isGenerating) {
          setIsGenerating(false);
          fetchDomainsByClient(clientId);
        }
      }, 120000);
    } catch (error) {
      console.error('Failed to queue domain generation:', error);
      toast.error('Failed to queue domain generation');
      setIsGenerating(false);
    }
  };

  const handleGenerateInboxes = async (domainId: string) => {
    if (!client.onboardingData) {
      toast.error('Please complete onboarding first');
      return;
    }
    const domain = domains.find((d) => d.id === domainId);
    if (!domain) return;

    const generated = await generateInboxesFromOnboarding(clientId, domainId, domain.domain, client.onboardingData);
    toast.success(`Generated ${generated.length} inbox suggestions for ${domain.domain}`);
  };

  const handleApproveAllDomains = () => {
    const pendingList = domains.filter((d) => d.status === 'pending_approval');
    pendingList.forEach((domain) => approveDomain(domain.id));
    toast.success(`Approved ${pendingList.length} domains`);
  };

  const handleApproveAllInboxes = () => {
    const pendingList = filteredInboxes.filter((i) => i.status === 'pending_approval');
    pendingList.forEach((inbox) => approveInbox(inbox.id));
    toast.success(`Approved ${pendingList.length} inboxes`);
  };

  const hasOnboardingData = Boolean(client.onboardingData);

  return (
    <TooltipProvider>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Package Fulfillment Dashboard - always visible above tabs */}
        <PackageFulfillmentDashboard
          subscription={subscription}
          inventoryDomainsCount={inventoryDomains.length}
          purchasedNeedingSetupCount={purchasedNeedingSetup.length}
          pendingDomainsCount={pendingDomainsCount}
          approvedDomainsCount={approvedDomainsCount}
          totalInboxesCount={allInboxes.length}
          entraDomainsActive={entraDomainsActive}
          googleDomainsActive={googleDomainsActive}
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

          {/* Procurement Tab - accordion workflow */}
          <TabsContent value="procurement">
            <div className="space-y-6">
              {/* Contextual header */}
              {subscription && subscription.domainsRemaining > 0 && (
                <Alert>
                  <Package className="h-4 w-4" />
                  <AlertDescription>
                    Your <strong>{subscription.packageTemplateName || 'Custom'}</strong> package needs <strong>{subscription.domainsRemaining} more domains</strong> to reach full capacity.
                  </AlertDescription>
                </Alert>
              )}

              <Accordion type="multiple" defaultValue={['domains', 'setup-inboxes']} className="space-y-4">
                {/* Domain Candidates — Generate + Review/Price/Purchase */}
                <AccordionItem value="domains" className="border rounded-lg px-4">
                  <AccordionTrigger className="hover:no-underline py-4">
                    <div className="flex items-center gap-3">
                      <Globe className="h-4 w-4 text-muted-foreground" />
                      <span className="text-base font-semibold">Domain Candidates</span>
                      {purchaseDomains.length > 0 && (
                        <div className="flex items-center gap-2">
                          {pendingDomainsCount > 0 && (
                            <span className="px-2 py-0.5 bg-yellow-50 text-yellow-700 rounded-full text-xs">{pendingDomainsCount} pending</span>
                          )}
                          {approvedDomainsCount > 0 && (
                            <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs">{approvedDomainsCount} approved</span>
                          )}
                        </div>
                      )}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="flex items-center gap-3 mb-4">
                      <Button
                        size="sm"
                        disabled={!canGenerateInfo?.canGenerate || isGenerating}
                        onClick={handleGenerateDomainsInline}
                      >
                        {isGenerating ? (
                          <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                        ) : (
                          <Sparkles className="h-4 w-4 mr-1" />
                        )}
                        {isGenerating ? 'Generating...' : 'Generate Domains'}
                      </Button>
                      {!canGenerateInfo?.canGenerate && canGenerateInfo?.message && (
                        <p className="text-xs text-muted-foreground">{canGenerateInfo.message}</p>
                      )}
                    </div>
                    {purchaseDomains.length > 0 ? (
                      <DomainCandidatesTable
                        domains={purchaseDomains}
                        clientId={clientId}
                        onDomainUpdate={() => fetchDomainsByClient(clientId)}
                      />
                    ) : (
                      <EmptyState
                        icon={Globe}
                        title="No domain candidates yet"
                        description="Click 'Generate Domains' above to create AI-powered domain suggestions."
                      />
                    )}
                  </AccordionContent>
                </AccordionItem>

                {/* Setup Inboxes */}
                <AccordionItem value="setup-inboxes" className="border rounded-lg px-4">
                  <AccordionTrigger className="hover:no-underline py-4">
                    <div className="flex items-center justify-between w-full pr-2">
                      <div className="flex items-center gap-3">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        <span className="text-base font-semibold">Setup Inboxes</span>
                        {purchasedNeedingSetup.length > 0 && (
                          <span className="px-2 py-0.5 bg-orange-50 text-orange-700 rounded-full text-xs">
                            {purchasedNeedingSetup.length} ready
                          </span>
                        )}
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    {purchasedNeedingSetup.length > 0 ? (
                      <DomainsNeedingSetupTable
                        domains={purchasedNeedingSetup}
                        onSetupClick={(selectedIds, override) => {
                          setSelectedDomainsForSetup(selectedIds);
                          setHasAgeOverride(override);
                          setShowInboxPurchaseWizard(true);
                        }}
                        onDomainsChange={() => fetchDomainsByClient(clientId)}
                      />
                    ) : (
                      <EmptyState
                        icon={Mail}
                        title="No domains awaiting inbox setup"
                        description="Domains will appear here once purchased above."
                      />
                    )}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </TabsContent>

          {/* Active Inventory Tab */}
          <TabsContent value="inventory">
            {/* Infrastructure Status */}
            <div className="mb-6 flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 text-green-700 rounded-full text-sm">
                <div className="h-2 w-2 rounded-full bg-green-500" />
                <span>Infrastructure Active</span>
              </div>
              {pendingInboxes > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-50 text-yellow-700 rounded-full text-sm">
                  <AlertTriangle className="h-3 w-3" />
                  <span>{pendingInboxes} inboxes pending approval</span>
                </div>
              )}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button className="text-muted-foreground hover:text-foreground">
                    <Info className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="max-w-xs">
                    Active domains and their inboxes. Go to &quot;Procurement&quot; to add more.
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>

            {/* Empty State for Inventory */}
            {inventoryDomains.length === 0 && (
              <Alert className="mb-6">
                <Sparkles className="h-4 w-4" />
                <AlertDescription>
                  <strong>No active domains yet.</strong> Go to the &quot;Procurement&quot; tab to generate
                  domain suggestions, check pricing, and purchase domains.
                </AlertDescription>
              </Alert>
            )}

            {/* Domain/Inbox Tree View */}
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
                  <EmptyState
                    icon={Globe}
                    title="No active domains"
                    description="Go to the 'Procurement' tab to generate and purchase domains."
                  />
                ) : (
                  <DomainInboxTree
                    domains={inventoryDomains}
                    inboxes={allInboxes}
                    onExpandDomain={handleExpandDomain}
                    loadingDomainIds={loadingDomainIds}
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Jobs Tab - Purchase Job History */}
          <TabsContent value="jobs">
            <PurchaseJobsTable
              clientId={clientId}
              onJobRetried={() => {
                // Refresh domains after a job is retried
                fetchDomainsByClient(clientId);
              }}
            />
          </TabsContent>
        </Tabs>

        {/* Forms */}
        <DomainForm
          clientId={clientId}
          open={showDomainForm}
          onOpenChange={setShowDomainForm}
        />
        <InboxForm
          clientId={clientId}
          open={showInboxForm}
          onOpenChange={setShowInboxForm}
        />

        {/* Edit Modals */}
        <DomainEditModal
          domain={editingDomain}
          open={editingDomain !== null}
          onOpenChange={(open) => !open && setEditingDomain(null)}
        />
        <InboxEditModal
          inbox={editingInbox}
          domains={domains}
          open={editingInbox !== null}
          onOpenChange={(open) => !open && setEditingInbox(null)}
        />

        {/* Inbox Provision Modal (One-Click Smart Provisioning) */}
        {client && (
          <InboxProvisionModal
            open={showInboxPurchaseWizard}
            onOpenChange={(open) => {
              setShowInboxPurchaseWizard(open);
              if (!open) {
                setSelectedDomainsForSetup([]);
                setHasAgeOverride(false);
              }
            }}
            clientId={clientId}
            clientName={client.name}
            selectedDomainIds={selectedDomainsForSetup}
            hasAgeOverride={hasAgeOverride}
            onSuccess={() => {
              fetchDomainsByClient(clientId);
              fetchInboxesByClient(clientId);
              setSelectedDomainsForSetup([]);
              setHasAgeOverride(false);
            }}
          />
        )}
      </PageContainer>
    </TooltipProvider>
  );
}
