'use client';

import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Plus, Megaphone, Loader2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { EmptyState } from '@/components/shared';
import {
  CampaignSidebar,
  CampaignHeader,
  StatsRow,
  LeadsTable,
  UploadModal,
  LeadSourceSelector,
  ScriptPullModal,
} from '@/components/leads';
import type { LeadSourceOption } from '@/components/leads';
import { useClientStore, useCampaignStore } from '@/lib/stores';

export default function LeadsPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const isLoadingClients = useClientStore((state) => state.isLoading);

  const campaigns = useCampaignStore((state) => state.campaigns);
  const leads = useCampaignStore((state) => state.leads);
  const isLoading = useCampaignStore((state) => state.isLoading);
  const error = useCampaignStore((state) => state.error);
  const fetchCampaignsByClient = useCampaignStore((state) => state.fetchCampaignsByClient);
  const fetchLeadsByCampaign = useCampaignStore((state) => state.fetchLeadsByCampaign);
  const runCampaign = useCampaignStore((state) => state.runCampaign);
  const pauseCampaign = useCampaignStore((state) => state.pauseCampaign);
  const simulateUploadLeads = useCampaignStore((state) => state.simulateUploadLeads);

  const client = getClient(clientId);
  const clientCampaigns = useMemo(
    () => campaigns.filter((c) => c.clientId === clientId),
    [campaigns, clientId]
  );

  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [sourceSelectOpen, setSourceSelectOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [scriptPullOpen, setScriptPullOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<LeadSourceOption>('upload');

  // Fetch campaigns on mount
  useEffect(() => {
    selectClient(clientId);
    fetchCampaignsByClient(clientId);
    // Also fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchCampaignsByClient, fetchClients, clients.length]);

  // Compute effective campaign ID (selected or first available)
  const effectiveCampaignId = selectedCampaignId ?? clientCampaigns[0]?.id ?? null;

  // Fetch leads when campaign is selected
  useEffect(() => {
    if (effectiveCampaignId) {
      fetchLeadsByCampaign(effectiveCampaignId);
    }
  }, [effectiveCampaignId, fetchLeadsByCampaign]);

  const selectedCampaign = useMemo(
    () => clientCampaigns.find((c) => c.id === effectiveCampaignId) ?? null,
    [clientCampaigns, effectiveCampaignId]
  );

  const campaignLeads = useMemo(
    () => (effectiveCampaignId ? leads.filter((l) => l.campaignId === effectiveCampaignId) : []),
    [leads, effectiveCampaignId]
  );

  // Loading state
  if ((isLoading || isLoadingClients) && clientCampaigns.length === 0) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  // Error state
  if (error && clientCampaigns.length === 0) {
    return (
      <PageContainer>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center gap-2">
            Failed to load campaigns: {error}
            <Button variant="link" size="sm" onClick={() => fetchCampaignsByClient(clientId)}>
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

  const handleRun = () => {
    if (effectiveCampaignId) {
      runCampaign(effectiveCampaignId);
      toast.success('Campaign started!');
    }
  };

  const handlePause = () => {
    if (effectiveCampaignId) {
      pauseCampaign(effectiveCampaignId);
      toast.info('Campaign paused');
    }
  };

  const handleUpload = (count: number) => {
    if (effectiveCampaignId) {
      simulateUploadLeads(effectiveCampaignId, count);
    }
  };

  const handleSourceProceed = () => {
    setSourceSelectOpen(false);
    if (selectedSource === 'upload') {
      setUploadModalOpen(true);
    } else {
      setScriptPullOpen(true);
    }
  };

  const handleAddLeads = () => {
    setSelectedSource('upload');
    setSourceSelectOpen(true);
  };

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {clientCampaigns.length === 0 ? (
          <Card>
            <CardContent className="py-12">
              <EmptyState
                icon={Megaphone}
                title="No campaigns yet"
                description="Create and approve campaign ideas in the Strategy tab to get started."
              />
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-12 gap-6">
            {/* Sidebar */}
            <div className="col-span-12 lg:col-span-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Campaigns</CardTitle>
                </CardHeader>
                <CardContent>
                  <CampaignSidebar
                    campaigns={clientCampaigns}
                    selectedId={effectiveCampaignId}
                    onSelect={setSelectedCampaignId}
                  />
                </CardContent>
              </Card>
            </div>

            {/* Main Content */}
            <div className="col-span-12 lg:col-span-9">
              {selectedCampaign ? (
                <Card>
                  <CardContent className="p-6">
                    <CampaignHeader
                      campaign={selectedCampaign}
                      onRun={handleRun}
                      onPause={handlePause}
                    />

                    <StatsRow campaign={selectedCampaign} />

                    <div className="flex items-center justify-between py-4 border-b">
                      <h3 className="font-semibold">Leads</h3>
                      <Button onClick={handleAddLeads}>
                        <Plus className="h-4 w-4 mr-2" />
                        Add Leads
                      </Button>
                    </div>

                    <div className="pt-4">
                      {campaignLeads.length === 0 ? (
                        <EmptyState
                          icon={Plus}
                          title="No leads yet"
                          description="Upload a CSV or pull leads from external sources."
                          action={{
                            label: 'Add Leads',
                            onClick: handleAddLeads,
                          }}
                        />
                      ) : (
                        <LeadsTable leads={campaignLeads} />
                      )}
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="py-12">
                    <EmptyState
                      icon={Megaphone}
                      title="Select a campaign"
                      description="Choose a campaign from the sidebar to view leads."
                    />
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* Lead Source Selection Modal */}
        <Dialog open={sourceSelectOpen} onOpenChange={setSourceSelectOpen}>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>Add Leads</DialogTitle>
              <DialogDescription>
                Choose how you want to add leads to &quot;{selectedCampaign?.name || 'this campaign'}&quot;
              </DialogDescription>
            </DialogHeader>
            <LeadSourceSelector
              selectedSource={selectedSource}
              onSourceChange={setSelectedSource}
              onProceed={handleSourceProceed}
              campaignSegment={selectedCampaign?.segment}
              campaignIndustry={selectedCampaign?.industry}
            />
          </DialogContent>
        </Dialog>

        {/* Upload Modal */}
        {selectedCampaign && (
          <UploadModal
            open={uploadModalOpen}
            onOpenChange={setUploadModalOpen}
            onUpload={handleUpload}
            campaignName={selectedCampaign.name}
          />
        )}

        {/* Script Pull Modal */}
        {selectedCampaign && (
          <ScriptPullModal
            open={scriptPullOpen}
            onOpenChange={setScriptPullOpen}
            campaign={selectedCampaign}
          />
        )}
      </PageContainer>
    </>
  );
}
