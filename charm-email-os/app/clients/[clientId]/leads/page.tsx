'use client';

import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Plus, Megaphone } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

  const { getClient, selectClient } = useClientStore();
  const { getCampaignsByClient, getLeadsByCampaign, runCampaign, pauseCampaign, simulateUploadLeads } =
    useCampaignStore();

  const client = getClient(clientId);
  const campaigns = useMemo(
    () => getCampaignsByClient(clientId),
    [getCampaignsByClient, clientId]
  );

  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [sourceSelectOpen, setSourceSelectOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [scriptPullOpen, setScriptPullOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<LeadSourceOption>('upload');

  // Compute effective campaign ID (selected or first available)
  const effectiveCampaignId = selectedCampaignId ?? campaigns[0]?.id ?? null;

  const selectedCampaign = useMemo(
    () => campaigns.find((c) => c.id === effectiveCampaignId) ?? null,
    [campaigns, effectiveCampaignId]
  );

  const leads = useMemo(
    () => (effectiveCampaignId ? getLeadsByCampaign(effectiveCampaignId) : []),
    [getLeadsByCampaign, effectiveCampaignId]
  );

  useEffect(() => {
    selectClient(clientId);
  }, [clientId, selectClient]);

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
        {campaigns.length === 0 ? (
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
                    campaigns={campaigns}
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
                      {leads.length === 0 ? (
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
                        <LeadsTable leads={leads} />
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
