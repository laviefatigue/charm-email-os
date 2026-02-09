'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { useClientStore } from '@/lib/stores';
import { ClientProfileCard } from '@/components/clients/ClientProfileCard';
import { SubmissionsList } from '@/components/clients/SubmissionsList';
import { SubscriptionCard } from '@/components/clients/SubscriptionCard';
import { SubscriptionEditModal } from '@/components/clients/SubscriptionEditModal';
import { SenderNamesTab } from '@/components/inboxes';
import { subscriptionApi } from '@/lib/api';
import type { SubscriptionWithUsage } from '@/lib/types';

export default function ProfilePage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient } = useClientStore();
  const client = getClient(clientId);

  const [showEditModal, setShowEditModal] = useState(false);
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);
  const [subscriptionKey, setSubscriptionKey] = useState(0); // For forcing refresh

  useEffect(() => {
    selectClient(clientId);
  }, [clientId, selectClient]);

  // Load subscription for the edit modal
  const loadSubscription = useCallback(async () => {
    try {
      const sub = await subscriptionApi.getClientSubscription(clientId);
      setSubscription(sub);
    } catch (err) {
      console.error('Failed to load subscription:', err);
    }
  }, [clientId]);

  useEffect(() => {
    loadSubscription();
  }, [loadSubscription]);

  const handleEditSubscription = () => {
    setShowEditModal(true);
  };

  const handleSubscriptionSaved = () => {
    loadSubscription();
    setSubscriptionKey(prev => prev + 1); // Force SubscriptionCard to refresh
  };

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Client not found</p>
        </div>
      </PageContainer>
    );
  }

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Basic Information Card */}
        <div className="mb-6">
          <ClientProfileCard client={client} />
        </div>

        {/* Package & Subscription Card */}
        <div className="mb-6">
          <SubscriptionCard
            key={subscriptionKey}
            clientId={clientId}
            onEdit={handleEditSubscription}
          />
        </div>

        {/* Sender Names */}
        <div className="mb-6">
          <SenderNamesTab
            clientId={clientId}
            client={client}
            onSave={() => {}}
          />
        </div>

        {/* Onboarding Submissions List */}
        <div className="mb-6">
          <SubmissionsList clientId={clientId} />
        </div>
      </PageContainer>

      {/* Subscription Edit Modal */}
      <SubscriptionEditModal
        open={showEditModal}
        onOpenChange={setShowEditModal}
        clientId={clientId}
        subscription={subscription}
        onSave={handleSubscriptionSaved}
      />
    </>
  );
}
