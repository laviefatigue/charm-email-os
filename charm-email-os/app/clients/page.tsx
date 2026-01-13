'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageContainer } from '@/components/layout';
import { ClientCard, ClientForm } from '@/components/clients';
import { EmptyState } from '@/components/shared';
import { useClientStore } from '@/lib/stores';

export default function ClientsPage() {
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const { clients } = useClientStore();

  const handleClientCreated = (clientId: string) => {
    router.push(`/clients/${clientId}`);
  };

  return (
    <PageContainer>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Clients</h1>
          <p className="text-muted-foreground">Manage your agency clients and their campaigns</p>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Client
        </Button>
      </div>

      {clients.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No clients yet"
          description="Get started by adding your first client to manage their email campaigns."
          action={{
            label: 'Add Client',
            onClick: () => setShowForm(true),
          }}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((client) => (
            <ClientCard key={client.id} client={client} />
          ))}
        </div>
      )}

      <ClientForm
        open={showForm}
        onOpenChange={setShowForm}
        onSuccess={handleClientCreated}
      />
    </PageContainer>
  );
}
