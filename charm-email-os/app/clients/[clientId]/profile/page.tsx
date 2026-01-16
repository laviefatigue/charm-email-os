'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { ClientHeader, TabNavigation, PageContainer } from '@/components/layout';
import { useClientStore } from '@/lib/stores';
import { ClientProfileCard } from '@/components/clients/ClientProfileCard';
import { SubmissionsList } from '@/components/clients/SubmissionsList';

export default function ProfilePage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient } = useClientStore();
  const client = getClient(clientId);

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

  return (
    <>
      <ClientHeader client={client} />
      <TabNavigation clientId={clientId} />

      <PageContainer>
        {/* Basic Information Card */}
        <div className="mb-6">
          <ClientProfileCard client={client} />
        </div>

        {/* Onboarding Submissions List */}
        <div className="mb-6">
          <SubmissionsList clientId={clientId} />
        </div>
      </PageContainer>
    </>
  );
}
