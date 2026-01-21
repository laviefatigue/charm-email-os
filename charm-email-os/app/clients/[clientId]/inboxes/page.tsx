'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Plus, Globe, Mail, Info, Sparkles, AlertTriangle, CheckCheck, Loader2, AlertCircle, ShoppingCart, Package } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
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
import { DomainSourcingWizard, InboxPurchaseWizard } from '@/components/purchasing';
import { useClientStore, useInfrastructureStore } from '@/lib/stores';
import { domainSourcingApi, type CanGenerateResponse } from '@/lib/api';
import type { Domain, Inbox } from '@/lib/types';

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

  // Inventory domains: purchased or active (domains we own)
  const inventoryDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'purchased' || d.status === 'active' || d.status === 'warming' || d.status === 'flagged' || d.status === 'dead')
  ), [allDomains, clientId]);

  // Purchase domains: pending approval or approved (domains to review/buy)
  const purchaseDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'pending' || d.status === 'pending_approval' || d.status === 'approved')
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
  const [activeTab, setActiveTab] = useState<string>('inventory');
  const [showDomainSourcingWizard, setShowDomainSourcingWizard] = useState(false);
  const [showInboxPurchaseWizard, setShowInboxPurchaseWizard] = useState(false);
  const [canGenerateInfo, setCanGenerateInfo] = useState<CanGenerateResponse | null>(null);

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
        {/* Tab Navigation */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="inventory" className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Current Inventory
            </TabsTrigger>
            <TabsTrigger value="purchase" className="flex items-center gap-2">
              <ShoppingCart className="h-4 w-4" />
              Purchase New
            </TabsTrigger>
          </TabsList>

          {/* Current Inventory Tab */}
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
                This shows your purchased domains and their inboxes.
                Go to &quot;Purchase New&quot; to add more domains.
              </p>
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Empty State for Inventory */}
        {inventoryDomains.length === 0 && (
          <Alert className="mb-6">
            <Sparkles className="h-4 w-4" />
            <AlertDescription>
              <strong>No purchased domains yet.</strong> Go to the &quot;Purchase New&quot; tab to generate
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
                title="No purchased domains"
                description="Go to the 'Purchase New' tab to generate and purchase domains."
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

          {/* Purchase New Tab */}
          <TabsContent value="purchase">
            <div className="space-y-6">
              {/* Status Summary */}
              <div className="flex items-center gap-4 flex-wrap">
                {pendingDomainsCount > 0 && (
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-50 text-yellow-700 rounded-full text-sm">
                    <AlertTriangle className="h-3 w-3" />
                    <span>{pendingDomainsCount} domains pending approval</span>
                  </div>
                )}
                {approvedDomainsCount > 0 && (
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-full text-sm">
                    <CheckCheck className="h-3 w-3" />
                    <span>{approvedDomainsCount} domains ready to purchase</span>
                  </div>
                )}
              </div>

              {/* Domain Candidates List */}
              {purchaseDomains.length > 0 && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="text-base font-semibold flex items-center gap-2">
                          <Globe className="h-4 w-4" />
                          Domain Candidates
                        </CardTitle>
                        <CardDescription className="mt-1">
                          Review and approve domains, then check pricing and purchase
                        </CardDescription>
                      </div>
                      <Button
                        size="sm"
                        variant="default"
                        disabled={!canGenerateInfo?.canGenerate}
                        onClick={() => setShowDomainSourcingWizard(true)}
                      >
                        <Sparkles className="h-4 w-4 mr-1" />
                        Generate More
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {purchaseDomains.map((domain) => (
                        <div
                          key={domain.id}
                          className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50"
                        >
                          <div className="flex items-center gap-3">
                            <Globe className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{domain.domain || domain.domainName}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              domain.status === 'approved'
                                ? 'bg-blue-100 text-blue-700'
                                : 'bg-yellow-100 text-yellow-700'
                            }`}>
                              {domain.status === 'approved' ? 'Approved' : 'Pending'}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            {(domain.status === 'pending' || domain.status === 'pending_approval') && (
                              <>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => approveDomain(domain.id)}
                                >
                                  <CheckCheck className="h-3 w-3 mr-1" />
                                  Approve
                                </Button>
                              </>
                            )}
                            {domain.status === 'approved' && (
                              <Button
                                size="sm"
                                variant="default"
                                onClick={() => setShowDomainSourcingWizard(true)}
                              >
                                <ShoppingCart className="h-3 w-3 mr-1" />
                                Check Price
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Empty State */}
              {purchaseDomains.length === 0 && (
                <Card>
                  <CardContent className="py-8">
                    <EmptyState
                      icon={Globe}
                      title="No domain candidates"
                      description="Generate domain suggestions to get started with purchasing."
                    />
                    <div className="flex justify-center mt-4">
                      <Button
                        disabled={!canGenerateInfo?.canGenerate}
                        onClick={() => setShowDomainSourcingWizard(true)}
                      >
                        <Sparkles className="h-4 w-4 mr-2" />
                        Start Domain Sourcing
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Inbox Purchasing Card - Only show when we have purchased domains */}
              {approvedDomains.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Mail className="h-5 w-5" />
                      Step 2: Purchase Inboxes
                    </CardTitle>
                    <CardDescription>
                      Generate inbox names and purchase from HyperTide (Entra or Google)
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="text-sm text-muted-foreground">
                        <ul className="space-y-2">
                          <li className="flex items-center gap-2">
                            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                            Entra: 100 inboxes/order (2 domains × 50 inboxes)
                          </li>
                          <li className="flex items-center gap-2">
                            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                            Google: 15 inboxes/order (5 domains × 3 inboxes)
                          </li>
                          <li className="flex items-center gap-2">
                            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                            Automatic EmailBison integration
                          </li>
                        </ul>
                      </div>
                      <Button
                        className="w-full"
                        onClick={() => setShowInboxPurchaseWizard(true)}
                      >
                        <ShoppingCart className="h-4 w-4 mr-2" />
                        Purchase Inboxes
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Summary Stats */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Domain Pipeline Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="text-center p-3 bg-yellow-50 rounded-lg">
                      <div className="text-2xl font-bold text-yellow-700">{pendingDomainsCount}</div>
                      <div className="text-xs text-yellow-600">Pending Approval</div>
                    </div>
                    <div className="text-center p-3 bg-blue-50 rounded-lg">
                      <div className="text-2xl font-bold text-blue-700">{approvedDomainsCount}</div>
                      <div className="text-xs text-blue-600">Ready to Purchase</div>
                    </div>
                    <div className="text-center p-3 bg-green-50 rounded-lg">
                      <div className="text-2xl font-bold text-green-700">{inventoryDomains.length}</div>
                      <div className="text-xs text-green-600">Purchased</div>
                    </div>
                    <div className="text-center p-3 bg-muted rounded-lg">
                      <div className="text-2xl font-bold">{allInboxes.length}</div>
                      <div className="text-xs text-muted-foreground">Total Inboxes</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
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

        {/* Domain Sourcing Wizard */}
        {client && (
          <DomainSourcingWizard
            open={showDomainSourcingWizard}
            onOpenChange={setShowDomainSourcingWizard}
            clientId={clientId}
            clientName={client.name}
            onComplete={(purchasedDomains) => {
              toast.success(`Purchased ${purchasedDomains.length} domains!`);
              // Refresh domains list
              fetchDomainsByClient(clientId);
            }}
          />
        )}

        {/* Inbox Purchase Wizard */}
        {client && (
          <InboxPurchaseWizard
            open={showInboxPurchaseWizard}
            onOpenChange={setShowInboxPurchaseWizard}
            clientId={clientId}
            clientName={client.name}
            forwardingDomain={client.onboardingData?.primaryDomain || client.name.toLowerCase().replace(/\s+/g, '') + '.com'}
            domains={approvedDomains.map(d => ({
              id: d.id,
              domainName: d.domain,
              status: d.status,
              inboxCount: allInboxes.filter(i => i.domainId === d.id).length,
            }))}
            onComplete={(totalInboxes) => {
              toast.success(`Created ${totalInboxes} inboxes!`);
              // Refresh inboxes list
              fetchInboxesByClient(clientId);
            }}
          />
        )}
      </PageContainer>
    </TooltipProvider>
  );
}
