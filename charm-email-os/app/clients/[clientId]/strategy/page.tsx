'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Target, FileText } from 'lucide-react';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import {
  ComprehensiveOnboarding,
  CampaignSequences,
  CycleNavigator,
  ActiveCycleCard,
  ProfileSelector,
  StrategySelector,
} from '@/components/strategy';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useClientStore } from '@/lib/stores';
import { strategyApi, type CampaignCycle, type CampaignSequence } from '@/lib/api';
import { toast } from 'sonner';

export default function StrategyPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const client = getClient(clientId);

  // Tab state
  const [activeTab, setActiveTab] = useState<string>('strategy');

  // Profile/Submission selection state
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<string | null>(null);

  // Strategy selection state (for Campaigns tab)
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<string | null>(null);

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

  // Fetch cycles (optionally filtered by strategy)
  const fetchCycles = useCallback(async () => {
    try {
      setCyclesLoading(true);
      setCyclesError(null);
      // Pass strategyId to filter cycles if selected
      const response = await strategyApi.getCycles(clientId, selectedStrategyId || undefined);
      setCycles(response.cycles);

      // Auto-select active cycle or first cycle
      const activeCycle = response.cycles.find((c) => c.status === 'active');
      if (activeCycle) {
        setActiveCycleId(activeCycle.id);
      } else if (response.cycles.length > 0) {
        setActiveCycleId(response.cycles[0].id);
      } else {
        setActiveCycleId(null);
      }
    } catch (err) {
      console.warn('Cycles API not available:', err);
      setCyclesError('Cycles not available');
    } finally {
      setCyclesLoading(false);
    }
  }, [clientId, selectedStrategyId]);

  useEffect(() => {
    if (clientId) {
      fetchCycles();
    }
  }, [clientId, fetchCycles]);

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

  // Handle strategy generation from Strategy tab
  const handleGenerate = useCallback(async (submissionId: string) => {
    setGenerating(true);
    setGenerationStatus('Starting generation...');

    try {
      // Start generation job with specific submission
      const response = await strategyApi.createJob(clientId, submissionId);
      const jobId = response.jobId;

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 60; // 5 minutes max (5 seconds * 60)

      const pollStatus = async () => {
        try {
          const status = await strategyApi.getJobStatus(jobId);
          setGenerationStatus(status.status);

          if (status.status === 'completed' || status.status === 'review') {
            // Refresh cycles data
            const cyclesResponse = await strategyApi.getCycles(clientId);
            setCycles(cyclesResponse.cycles);

            // Select the newest cycle
            if (cyclesResponse.cycles.length > 0) {
              const newestCycle = cyclesResponse.cycles[0];
              setActiveCycleId(newestCycle.id);
            }

            // Auto-switch to Campaigns tab
            setActiveTab('campaigns');
            toast.success('Strategy generated successfully!');
            setGenerating(false);
            setGenerationStatus(null);
            return;
          }

          if (status.status === 'failed') {
            throw new Error(status.errorMessage || 'Generation failed');
          }

          // Continue polling
          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(pollStatus, 5000);
          } else {
            throw new Error('Generation timed out');
          }
        } catch (err) {
          console.error('Poll error:', err);
          toast.error('Failed to check generation status');
          setGenerating(false);
          setGenerationStatus(null);
        }
      };

      // Start polling after a short delay
      setTimeout(pollStatus, 2000);
    } catch (error) {
      console.error('Generation error:', error);
      toast.error('Failed to start generation');
      setGenerating(false);
      setGenerationStatus(null);
    }
  }, [clientId]);

  // Handle campaign generation for an existing cycle (from campaign tiles)
  const handleGenerateCycleCampaigns = useCallback(async () => {
    if (!activeCycleId) {
      toast.error('No cycle selected');
      return;
    }

    setGenerating(true);
    setGenerationStatus('Starting campaign generation...');

    try {
      // Start generation job for this cycle
      const response = await strategyApi.generateCycleCampaigns(
        activeCycleId,
        selectedSubmissionId || undefined
      );
      const jobId = response.jobId;

      toast.success('Campaign generation started');

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 120; // 10 minutes max (5 seconds * 120)

      const pollStatus = async () => {
        try {
          const status = await strategyApi.getJobStatus(jobId);
          setGenerationStatus(status.status);

          if (status.status === 'completed' || status.status === 'review') {
            // Refresh campaigns for this cycle
            const campaignsResponse = await strategyApi.getCampaignsForCycle(activeCycleId);
            setCycleCampaigns(campaignsResponse.campaigns);

            toast.success('Campaigns generated successfully!');
            setGenerating(false);
            setGenerationStatus(null);
            return;
          }

          if (status.status === 'failed') {
            throw new Error(status.errorMessage || 'Generation failed');
          }

          // Continue polling
          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(pollStatus, 5000);
          } else {
            throw new Error('Generation timed out');
          }
        } catch (err) {
          console.error('Poll error:', err);
          toast.error('Failed to check generation status');
          setGenerating(false);
          setGenerationStatus(null);
        }
      };

      // Start polling after a short delay
      setTimeout(pollStatus, 2000);
    } catch (error) {
      console.error('Generation error:', error);
      toast.error('Failed to start campaign generation');
      setGenerating(false);
      setGenerationStatus(null);
    }
  }, [activeCycleId, selectedSubmissionId]);

  // Handle adding a new cycle and generating campaigns for it
  const handleAddCycleAndGenerate = useCallback(async () => {
    setGenerating(true);
    setGenerationStatus('Creating new cycle...');

    try {
      // Calculate next cycle number
      const nextCycleNumber = cycles.length > 0
        ? Math.max(...cycles.map(c => c.cycleNumber)) + 1
        : 1;

      // Create new cycle
      const newCycle = await strategyApi.createCycle(clientId, {
        cycleNumber: nextCycleNumber,
        targetCampaigns: 4,
      });

      toast.success(`Cycle ${nextCycleNumber} created`);

      // Refresh cycles list and select the new cycle
      const cyclesResponse = await strategyApi.getCycles(clientId, selectedStrategyId || undefined);
      setCycles(cyclesResponse.cycles);
      setActiveCycleId(newCycle.id);

      // Now generate campaigns for the new cycle
      setGenerationStatus('Starting campaign generation...');
      const response = await strategyApi.generateCycleCampaigns(
        newCycle.id,
        selectedSubmissionId || undefined
      );
      const jobId = response.jobId;

      toast.success('Campaign generation started');

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 120;

      const pollStatus = async () => {
        try {
          const status = await strategyApi.getJobStatus(jobId);
          setGenerationStatus(status.status);

          if (status.status === 'completed' || status.status === 'review') {
            const campaignsResponse = await strategyApi.getCampaignsForCycle(newCycle.id);
            setCycleCampaigns(campaignsResponse.campaigns);

            toast.success('Campaigns generated successfully!');
            setGenerating(false);
            setGenerationStatus(null);
            return;
          }

          if (status.status === 'failed') {
            throw new Error(status.errorMessage || 'Generation failed');
          }

          attempts++;
          if (attempts < maxAttempts) {
            setTimeout(pollStatus, 5000);
          } else {
            throw new Error('Generation timed out');
          }
        } catch (err) {
          console.error('Poll error:', err);
          toast.error('Failed to check generation status');
          setGenerating(false);
          setGenerationStatus(null);
        }
      };

      setTimeout(pollStatus, 2000);
    } catch (error) {
      console.error('Add cycle error:', error);
      toast.error('Failed to create cycle');
      setGenerating(false);
      setGenerationStatus(null);
    }
  }, [clientId, cycles, selectedStrategyId, selectedSubmissionId]);

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
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList>
            <TabsTrigger value="strategy" className="gap-2">
              <FileText className="w-4 h-4" />
              Strategy
            </TabsTrigger>
            <TabsTrigger value="campaigns" className="gap-2">
              <Target className="w-4 h-4" />
              Campaigns
            </TabsTrigger>
          </TabsList>

          {/* Strategy Tab - Client strategy input with Generate button */}
          <TabsContent value="strategy" className="space-y-4">
            {/* Profile Selector - allows choosing between multiple submissions */}
            <ProfileSelector
              clientId={clientId}
              selectedSubmissionId={selectedSubmissionId}
              onSelect={setSelectedSubmissionId}
            />

            {/* Comprehensive Strategy Form - shows the selected submission */}
            <ComprehensiveOnboarding
              clientId={clientId}
              submissionId={selectedSubmissionId}
              onGenerate={handleGenerate}
              isGenerating={generating}
              generationStatus={generationStatus}
            />
          </TabsContent>

          {/* Campaigns Tab - Generated strategy view */}
          <TabsContent value="campaigns" className="space-y-6">
            {/* Strategy Selector - switch between generated strategies */}
            <div className="flex items-center justify-between">
              <StrategySelector
                clientId={clientId}
                selectedStrategyId={selectedStrategyId}
                onStrategyChange={setSelectedStrategyId}
              />
            </div>

            {/* Cycle Navigator - shows cycles for selected strategy */}
            {hasCycles && (
              <CycleNavigator
                cycles={cycles}
                activeCycleId={activeCycleId}
                onSelect={setActiveCycleId}
                onAddCycle={handleAddCycleAndGenerate}
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
                  console.log('Edit cycle clicked');
                }}
                onGenerateCampaigns={handleGenerateCycleCampaigns}
                isGenerating={generating}
              />
            )}

            {/* No cycles message */}
            {!hasCycles && !cyclesLoading && (
              <div className="text-center py-12 border rounded-lg bg-muted/20">
                <Target className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="font-medium mb-2">No campaigns generated yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Go to the Strategy tab and click Generate to create your first campaign cycle.
                </p>
              </div>
            )}

            {/* Campaign Sequences - filtered to selected cycle */}
            {hasCycles && (
              <CampaignSequences clientId={clientId} cycleId={activeCycleId || undefined} />
            )}
          </TabsContent>
        </Tabs>
      </PageContainer>
    </>
  );
}
