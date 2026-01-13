'use client';

import { useEffect, useRef } from 'react';
import { useClientStore, useInfrastructureStore, useStrategyStore, useCampaignStore } from '@/lib/stores';
import {
  mockClients,
  mockDomains,
  mockInboxes,
  mockCampaignIdeas,
  mockCampaigns,
  mockLeads,
} from '@/lib/mock-data';

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current) {
      // Initialize all stores with mock data
      useClientStore.getState().setClients(mockClients);
      useInfrastructureStore.getState().setDomains(mockDomains);
      useInfrastructureStore.getState().setInboxes(mockInboxes);
      useStrategyStore.getState().setIdeas(mockCampaignIdeas);
      useCampaignStore.getState().setCampaigns(mockCampaigns);
      useCampaignStore.getState().setLeads(mockLeads);

      initialized.current = true;
    }
  }, []);

  return <>{children}</>;
}
