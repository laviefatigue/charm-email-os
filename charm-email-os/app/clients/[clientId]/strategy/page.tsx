'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Lightbulb, Target, Building2 } from 'lucide-react';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import {
  ComprehensiveOnboarding,
  CampaignSequences,
  CycleNavigator,
  ActiveCycleCard,
} from '@/components/strategy';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useClientStore } from '@/lib/stores';
import { strategyApi, type CampaignCycle, type CampaignSequence } from '@/lib/api';

export default function StrategyPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const client = getClient(clientId);

  // Cycle state
  const [cycles, setCycles] = useState<CampaignCycle[]>([]);
  const [activeCycleId, setActiveCycleId] = useState<string | null>(null);
  const [cycleCampaigns, setCycleCampaigns] = useState<CampaignSequence[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [cyclesLoading, setCyclesLoading] = useState(true);
  const [cyclesError, setCyclesError] = useState<string | null>(null);

  useEffect(() => {
    selectClient(clientId);
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchClients, clients.length]);

  // Fetch cycles
  useEffect(() => {
    async function fetchCycles() {
      try {
        setCyclesLoading(true);
        setCyclesError(null);
        const response = await strategyApi.getCycles(clientId);
        setCycles(response.cycles);

        // Auto-select active cycle or first cycle
        const activeCycle = response.cycles.find((c) => c.status === 'active');
        if (activeCycle) {
          setActiveCycleId(activeCycle.id);
        } else if (response.cycles.length > 0) {
          setActiveCycleId(response.cycles[0].id);
        }
      } catch (err) {
        // Cycles API might not be implemented yet - gracefully handle
        console.warn('Cycles API not available:', err);
        setCyclesError('Cycles not available');
      } finally {
        setCyclesLoading(false);
      }
    }

    if (clientId) {
      fetchCycles();
    }
  }, [clientId]);

  // Fetch campaigns for active cycle
  useEffect(() => {
    async function fetchCycleCampaigns() {
      if (!activeCycleId) {
        setCycleCampaigns([]);
        return;
      }

      try {
        const response = await strategyApi.getCampaignsForCycle(activeCycleId);
        setCycleCampaigns(response.campaigns);
      } catch (err) {
        console.warn('Failed to fetch cycle campaigns:', err);
        setCycleCampaigns([]);
      }
    }

    fetchCycleCampaigns();
  }, [activeCycleId]);

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading client...</p>
        </div>
      </PageContainer>
    );
  }

  const activeCycle = cycles.find((c) => c.id === activeCycleId);
  const hasCycles = cycles.length > 0 && !cyclesError;

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        <Tabs defaultValue="campaigns" className="space-y-6">
          <TabsList>
            <TabsTrigger value="campaigns" className="gap-2">
              <Target className="w-4 h-4" />
              Campaigns
            </TabsTrigger>
            <TabsTrigger value="profile" className="gap-2">
              <Building2 className="w-4 h-4" />
              Profile Context
            </TabsTrigger>
          </TabsList>

          <TabsContent value="campaigns" className="space-y-6">
            {/* Cycle Navigator - only show if cycles are available */}
            {hasCycles && (
              <CycleNavigator
                cycles={cycles}
                activeCycleId={activeCycleId}
                onSelect={setActiveCycleId}
                onAddCycle={() => {
                  // TODO: Open create cycle modal
                  console.log('Add cycle clicked');
                }}
              />
            )}

            {/* Active Cycle Card - show if cycle is selected */}
            {hasCycles && activeCycle && (
              <ActiveCycleCard
                cycle={activeCycle}
                campaigns={cycleCampaigns}
                selectedCampaignId={selectedCampaignId}
                onSelectCampaign={setSelectedCampaignId}
                onEditCycle={() => {
                  // TODO: Open edit cycle modal
                  console.log('Edit cycle clicked');
                }}
                onGenerateCampaigns={() => {
                  // TODO: Trigger generation
                  console.log('Generate campaigns clicked');
                }}
              />
            )}

            {/* Campaign Sequences - existing component */}
            <CampaignSequences clientId={clientId} />
          </TabsContent>

          <TabsContent value="profile">
            <ComprehensiveOnboarding clientId={clientId} />
          </TabsContent>
        </Tabs>
      </PageContainer>
    </>
  );
}
