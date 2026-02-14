'use client';

import { useMemo, useCallback, useState, useEffect } from 'react';
import { useInfrastructureStore, useClientStore } from '@/lib/stores';
import { domainSourcingApi, subscriptionApi, type CanGenerateResponse } from '@/lib/api';
import type { Domain, Inbox, SubscriptionWithUsage } from '@/lib/types';

/**
 * Shared hook for inbox page state management.
 * Centralizes domain/inbox filtering and common callbacks used across tabs.
 */
export function useInboxPageState(clientId: string) {
  // Zustand store access
  const allDomains = useInfrastructureStore((state) => state.domains);
  const allStoreInboxes = useInfrastructureStore((state) => state.inboxes);
  const isLoading = useInfrastructureStore((state) => state.isLoading);
  const error = useInfrastructureStore((state) => state.error);
  const loadingDomainIds = useInfrastructureStore((state) => state.loadingDomainIds);
  const fetchDomainsByClient = useInfrastructureStore((state) => state.fetchDomainsByClient);
  const fetchInboxesByClient = useInfrastructureStore((state) => state.fetchInboxesByClient);
  const fetchInboxesForDomainLazy = useInfrastructureStore((state) => state.fetchInboxesForDomainLazy);

  const { getClient, selectClient, fetchClients, clients } = useClientStore();
  const isLoadingClients = useClientStore((state) => state.isLoading);
  const client = getClient(clientId);

  // Local state for subscription and can-generate info
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);
  const [canGenerateInfo, setCanGenerateInfo] = useState<CanGenerateResponse | null>(null);

  // Filter domains for this client
  const clientDomains = useMemo(
    () => allDomains.filter((d) => d.clientId === clientId),
    [allDomains, clientId]
  );

  // Filter inboxes for this client
  const clientInboxes = useMemo(
    () => allStoreInboxes.filter((i) => i.clientId === clientId),
    [allStoreInboxes, clientId]
  );

  // Domain status groups
  const domainsByStatus = useMemo(() => {
    // Inventory: active, legacy, warming, flagged, dead
    const inventory = clientDomains.filter((d) =>
      ['active', 'legacy', 'warming', 'flagged', 'dead'].includes(d.status)
    );

    // Candidates: available, pending, pending_approval, approved, rejected
    // Only show if they have pricing (or are purchased/provisioning)
    const candidates = clientDomains.filter(
      (d) =>
        ['available', 'pending', 'pending_approval', 'approved', 'rejected', 'purchased', 'provisioning'].includes(d.status) &&
        (d.cachedPrice != null || d.status === 'purchased' || d.status === 'provisioning')
    );

    // Purchased: need inbox setup
    const purchased = clientDomains.filter((d) =>
      ['purchased', 'provisioning'].includes(d.status)
    );

    // Approved: ready for inbox creation
    const approved = clientDomains.filter((d) =>
      ['purchased', 'active', 'warming'].includes(d.status)
    );

    // Pending approval count
    const pendingCount = clientDomains.filter((d) =>
      ['pending', 'pending_approval'].includes(d.status)
    ).length;

    // Approved count
    const approvedCount = clientDomains.filter((d) => d.status === 'approved').length;

    return {
      inventory,
      candidates,
      purchased,
      approved,
      pendingCount,
      approvedCount,
    };
  }, [clientDomains]);

  // Provider breakdown from inventory
  const providerBreakdown = useMemo(() => ({
    entra: domainsByStatus.inventory.filter((d) => d.infrastructureType === 'entra').length,
    google: domainsByStatus.inventory.filter((d) => d.infrastructureType === 'google').length,
  }), [domainsByStatus.inventory]);

  // Refresh callbacks
  const refreshDomains = useCallback(
    () => fetchDomainsByClient(clientId),
    [fetchDomainsByClient, clientId]
  );

  const refreshInboxes = useCallback(
    () => fetchInboxesByClient(clientId),
    [fetchInboxesByClient, clientId]
  );

  const refreshAll = useCallback(() => {
    refreshDomains();
    refreshInboxes();
  }, [refreshDomains, refreshInboxes]);

  // Wrapper for lazy inbox loading
  const handleExpandDomain = useCallback(
    (domainId: string) => {
      fetchInboxesForDomainLazy(domainId, clientId);
    },
    [fetchInboxesForDomainLazy, clientId]
  );

  // Fetch data on mount
  useEffect(() => {
    selectClient(clientId);
    fetchDomainsByClient(clientId);
    if (clients.length === 0) {
      fetchClients();
    }
  }, [clientId, selectClient, fetchDomainsByClient, fetchClients, clients.length]);

  // Fetch can-generate info
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

  // Fetch subscription
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

  return {
    // Client
    client,
    isLoadingClients,

    // Domains
    clientDomains,
    domainsByStatus,
    providerBreakdown,

    // Inboxes
    clientInboxes,

    // Loading states
    isLoading,
    error,
    loadingDomainIds,

    // Subscription & generation
    subscription,
    canGenerateInfo,

    // Callbacks
    refreshDomains,
    refreshInboxes,
    refreshAll,
    handleExpandDomain,
  };
}
