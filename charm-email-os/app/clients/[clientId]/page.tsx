'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useClientStore } from '@/lib/stores';
import { PageContainer } from '@/components/layout';
import { Loader2 } from 'lucide-react';

export default function ClientDetailPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.clientId as string;

  const { getClient, selectClient } = useClientStore();
  const client = getClient(clientId);

  useEffect(() => {
    if (client) {
      selectClient(clientId);
      // Always navigate to inboxes page
      router.replace(`/clients/${clientId}/inboxes`);
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

  return (
    <PageContainer>
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    </PageContainer>
  );
}
