'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useClientStore } from '@/lib/stores';
import { OnboardingForm } from '@/components/clients';
import { PageContainer } from '@/components/layout';

export default function ClientDetailPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.clientId as string;

  const { getClient, selectClient } = useClientStore();
  const client = getClient(clientId);

  // Modal state managed separately from derived condition
  const [onboardingDismissed, setOnboardingDismissed] = useState(false);

  // Determine if onboarding should be shown (derived from client state)
  const needsOnboarding = Boolean(client && !client.onboardingComplete);
  const showOnboarding = needsOnboarding && !onboardingDismissed;

  useEffect(() => {
    if (client) {
      selectClient(clientId);

      // Navigate to inboxes if onboarding is complete
      if (client.onboardingComplete) {
        router.replace(`/clients/${clientId}/inboxes`);
      }
    }
  }, [client, clientId, router, selectClient]);

  if (!client) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Client not found</p>
        </div>
      </PageContainer>
    );
  }

  const handleOnboardingComplete = () => {
    router.push(`/clients/${clientId}/inboxes`);
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setOnboardingDismissed(true);
    }
  };

  return (
    <>
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </PageContainer>

      <OnboardingForm
        client={client}
        open={showOnboarding}
        onOpenChange={handleOpenChange}
        onComplete={handleOnboardingComplete}
      />
    </>
  );
}
