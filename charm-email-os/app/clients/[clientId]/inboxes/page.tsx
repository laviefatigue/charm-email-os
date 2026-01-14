'use client';

import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Plus, Globe, Mail, Info, Sparkles, AlertTriangle, CheckCheck, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { EmptyState } from '@/components/shared';
import {
  DomainCard,
  InboxCard,
  DomainForm,
  InboxForm,
  DomainEditModal,
  InboxEditModal,
} from '@/components/inboxes';
import { useClientStore, useInfrastructureStore } from '@/lib/stores';
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
  const fetchDomainsByClient = useInfrastructureStore((state) => state.fetchDomainsByClient);
  const fetchInboxesByClient = useInfrastructureStore((state) => state.fetchInboxesByClient);
  const generateDomainsFromOnboarding = useInfrastructureStore((state) => state.generateDomainsFromOnboarding);
  const generateInboxesFromOnboarding = useInfrastructureStore((state) => state.generateInboxesFromOnboarding);
  const approveDomain = useInfrastructureStore((state) => state.approveDomain);
  const approveInbox = useInfrastructureStore((state) => state.approveInbox);

  const client = getClient(clientId);

  // Fetch data on mount
  useEffect(() => {
    selectClient(clientId);
    fetchDomainsByClient(clientId);
    fetchInboxesByClient(clientId);
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchDomainsByClient, fetchInboxesByClient, fetchClients, clients.length]);

  // Filter domains/inboxes for this client - now reactive because we subscribe to the arrays
  const domains = useMemo(() => allDomains.filter((d) => d.clientId === clientId), [allDomains, clientId]);
  const approvedDomains = useMemo(() => allDomains.filter(
    (d) => d.clientId === clientId && (d.status === 'approved' || d.status === 'active' || d.status === 'warming')
  ), [allDomains, clientId]);
  const allInboxes = useMemo(() => allStoreInboxes.filter((i) => i.clientId === clientId), [allStoreInboxes, clientId]);

  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);
  const [showDomainForm, setShowDomainForm] = useState(false);
  const [showInboxForm, setShowInboxForm] = useState(false);
  const [editingDomain, setEditingDomain] = useState<Domain | null>(null);
  const [editingInbox, setEditingInbox] = useState<Inbox | null>(null);

  const filteredInboxes = useMemo(() => {
    if (!selectedDomainId) return allInboxes;
    return allInboxes.filter((i) => i.domainId === selectedDomainId);
  }, [selectedDomainId, allInboxes]);

  // Count pending approvals
  const pendingDomains = domains.filter((d) => d.status === 'pending_approval').length;
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
        {/* Infrastructure Status */}
        <div className="mb-6 flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 text-green-700 rounded-full text-sm">
            <div className="h-2 w-2 rounded-full bg-green-500" />
            <span>Infrastructure Active</span>
          </div>
          {pendingDomains > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-50 text-yellow-700 rounded-full text-sm">
              <AlertTriangle className="h-3 w-3" />
              <span>{pendingDomains} domains pending approval</span>
            </div>
          )}
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
                Approve domains first, then create inboxes for approved domains.
                Rejected items can be edited and resubmitted.
              </p>
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Workflow Guide */}
        {domains.length === 0 && (
          <Alert className="mb-6">
            <Sparkles className="h-4 w-4" />
            <AlertDescription>
              <strong>Getting Started:</strong> Generate domain suggestions from your onboarding data,
              approve the ones you want, then generate inboxes for each approved domain.
            </AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Domains Column */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <Globe className="h-4 w-4" />
                      Domains
                    </CardTitle>
                    <CardDescription className="mt-1">
                      Approve domains before creating inboxes
                    </CardDescription>
                  </div>
                </div>
                <div className="flex gap-2 mt-3">
                  {hasOnboardingData && (
                    <Button
                      size="sm"
                      variant="default"
                      onClick={handleGenerateDomains}
                      className="flex-1"
                    >
                      <Sparkles className="h-4 w-4 mr-1" />
                      Generate
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowDomainForm(true)}
                    className={hasOnboardingData ? '' : 'flex-1'}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Manual
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {domains.length === 0 ? (
                  <EmptyState
                    icon={Globe}
                    title="No domains"
                    description={
                      hasOnboardingData
                        ? 'Click Generate to create domain suggestions from onboarding.'
                        : 'Complete onboarding or add domains manually.'
                    }
                  />
                ) : (
                  <>
                    <button
                      onClick={() => setSelectedDomainId(null)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedDomainId === null
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'text-muted-foreground hover:bg-muted'
                      }`}
                    >
                      All Domains ({domains.length})
                    </button>
                    {domains.map((domain) => (
                      <DomainCard
                        key={domain.id}
                        domain={domain}
                        isSelected={selectedDomainId === domain.id}
                        onSelect={() => setSelectedDomainId(domain.id)}
                        onEdit={setEditingDomain}
                      />
                    ))}
                    {pendingDomains > 0 && (
                      <Button
                        variant="default"
                        size="sm"
                        className="w-full mt-2"
                        onClick={handleApproveAllDomains}
                      >
                        <CheckCheck className="h-4 w-4 mr-2" />
                        Approve All ({pendingDomains})
                      </Button>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Inboxes Column */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <Mail className="h-4 w-4" />
                      Inboxes
                      {selectedDomainId && (
                        <span className="text-muted-foreground font-normal">
                          ({filteredInboxes.length} of {allInboxes.length})
                        </span>
                      )}
                    </CardTitle>
                    <CardDescription className="mt-1">
                      {approvedDomains.length === 0
                        ? 'Approve a domain first to create inboxes'
                        : 'Generate or add inboxes for approved domains'}
                    </CardDescription>
                  </div>
                </div>
                {approvedDomains.length > 0 && (
                  <div className="flex gap-2 mt-3">
                    {hasOnboardingData && selectedDomainId && approvedDomains.find(d => d.id === selectedDomainId) && (
                      <Button
                        size="sm"
                        variant="default"
                        onClick={() => handleGenerateInboxes(selectedDomainId)}
                      >
                        <Sparkles className="h-4 w-4 mr-1" />
                        Generate for Selected
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setShowInboxForm(true)}
                    >
                      <Plus className="h-4 w-4 mr-1" />
                      Add Inbox
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {approvedDomains.length === 0 ? (
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>
                      You need to approve at least one domain before creating inboxes.
                      Approve a domain from the list on the left.
                    </AlertDescription>
                  </Alert>
                ) : filteredInboxes.length === 0 ? (
                  <EmptyState
                    icon={Mail}
                    title="No inboxes"
                    description={
                      hasOnboardingData
                        ? 'Select an approved domain and click Generate to create inbox suggestions.'
                        : 'Add inboxes manually for your approved domains.'
                    }
                    action={{
                      label: 'Add Inbox',
                      onClick: () => setShowInboxForm(true),
                    }}
                  />
                ) : (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {filteredInboxes.map((inbox) => (
                        <InboxCard
                          key={inbox.id}
                          inbox={inbox}
                          onEdit={setEditingInbox}
                        />
                      ))}
                    </div>
                    {filteredInboxes.filter((i) => i.status === 'pending_approval').length > 0 && (
                      <Button
                        variant="default"
                        size="sm"
                        className="w-full mt-4"
                        onClick={handleApproveAllInboxes}
                      >
                        <CheckCheck className="h-4 w-4 mr-2" />
                        Approve All Inboxes ({filteredInboxes.filter((i) => i.status === 'pending_approval').length})
                      </Button>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

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
      </PageContainer>
    </TooltipProvider>
  );
}
