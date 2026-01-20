'use client';

import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Lightbulb, Sparkles, Megaphone, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { EmptyState } from '@/components/shared';
import {
  OnboardingSummary,
  ComprehensiveOnboarding,
  IdeaCard,
  IdeaEditModal,
  CreateCampaignModal,
  ApprovedCampaignRow,
  CampaignSuggestions,
} from '@/components/strategy';
import { useClientStore, useStrategyStore, useCampaignStore } from '@/lib/stores';
import type { CampaignIdea } from '@/lib/types';

export default function StrategyPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const { getIdeasByClient, getPendingIdeas, generateIdeas } = useStrategyStore();
  const { getCampaignsByClient } = useCampaignStore();

  const client = getClient(clientId);
  const _allIdeas = useMemo(() => getIdeasByClient(clientId), [getIdeasByClient, clientId]);
  void _allIdeas; // Keep for potential future use
  const pendingIdeas = useMemo(() => getPendingIdeas(clientId), [getPendingIdeas, clientId]);
  const campaigns = useMemo(() => getCampaignsByClient(clientId), [getCampaignsByClient, clientId]);

  const [editingIdea, setEditingIdea] = useState<CampaignIdea | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    selectClient(clientId);
    // Fetch clients if not loaded
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchClients, clients.length]);

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Client not found</p>
        </div>
      </PageContainer>
    );
  }

  const handleGenerateIdeas = async () => {
    if (!client.onboardingData) {
      toast.error('Please complete onboarding first');
      return;
    }

    setGenerating(true);

    // Simulate API delay
    await new Promise((resolve) => setTimeout(resolve, 1500));

    generateIdeas(
      clientId,
      client.onboardingData.industry,
      'Target Segment' // Would come from more detailed onboarding
    );

    toast.success('New campaign ideas generated!');
    setGenerating(false);
  };

  const handleEditIdea = (idea: CampaignIdea) => {
    setEditingIdea(idea);
  };

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Onboarding Summary - Quick view */}
        <div className="mb-6">
          <OnboardingSummary client={client} />
        </div>

        {/* Comprehensive Onboarding - Full form submission */}
        <div className="mb-6">
          <ComprehensiveOnboarding clientId={clientId} />
        </div>

        {/* AI-Generated Campaign Suggestions */}
        <div className="mb-6">
          <CampaignSuggestions clientId={clientId} />
        </div>

        {/* Campaign Ideas */}
        <Card className="mb-6">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Lightbulb className="h-4 w-4" />
                Campaign Ideas
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                AI-generated or manually created campaigns
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => setShowCreateModal(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Manual
              </Button>
              <Button onClick={handleGenerateIdeas} disabled={generating}>
                <Sparkles className="h-4 w-4 mr-2" />
                {generating ? 'Generating...' : 'Generate Ideas'}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {pendingIdeas.length === 0 ? (
              <EmptyState
                icon={Lightbulb}
                title="No pending ideas"
                description="Generate new campaign ideas based on your client profile."
                action={{
                  label: 'Generate Ideas',
                  onClick: handleGenerateIdeas,
                }}
              />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {pendingIdeas.map((idea) => (
                  <IdeaCard key={idea.id} idea={idea} onEdit={handleEditIdea} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Approved Campaigns */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Megaphone className="h-4 w-4" />
              Approved Campaigns ({campaigns.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {campaigns.length === 0 ? (
              <EmptyState
                icon={Megaphone}
                title="No campaigns yet"
                description="Approve campaign ideas above to create campaigns."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Campaign Name</TableHead>
                    <TableHead>Industry</TableHead>
                    <TableHead>Segment</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {campaigns.map((campaign) => (
                    <ApprovedCampaignRow
                      key={campaign.id}
                      campaign={campaign}
                      clientId={clientId}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Edit Modal */}
        <IdeaEditModal
          idea={editingIdea}
          open={!!editingIdea}
          onOpenChange={(open) => !open && setEditingIdea(null)}
        />

        {/* Create Campaign Modal */}
        <CreateCampaignModal
          client={client}
          open={showCreateModal}
          onOpenChange={setShowCreateModal}
        />
      </PageContainer>
    </>
  );
}
