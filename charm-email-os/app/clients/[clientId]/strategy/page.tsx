'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import {
  OnboardingSummary,
  ComprehensiveOnboarding,
  CampaignSuggestions,
  CampaignSequences,
} from '@/components/strategy';
import { useClientStore } from '@/lib/stores';

export default function StrategyPage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const client = getClient(clientId);

  useEffect(() => {
    selectClient(clientId);
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchClients, clients.length]);

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading client...</p>
        </div>
      </PageContainer>
    );
  }

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

        {/* AI-Generated 4-Email Campaign Sequences */}
        <div className="mb-6">
          <CampaignSequences clientId={clientId} />
        </div>

        {/* Legacy: Single-variant Campaign Suggestions from API */}
        <div className="mb-6">
          <CampaignSuggestions clientId={clientId} />
        </div>
      </PageContainer>
    </>
  );
}
