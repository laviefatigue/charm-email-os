'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Users, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { PageContainer } from '@/components/layout';
import { ClientCard, ClientForm } from '@/components/clients';
import { EmptyState } from '@/components/shared';
import { useClientStore } from '@/lib/stores';

export default function ClientsPage() {
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const { clients, isLoading, error, fetchClients } = useClientStore();

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  const handleClientCreated = (clientId: string) => {
    router.push(`/clients/${clientId}`);
  };

  // Loading state
  if (isLoading && clients.length === 0) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  // Error state
  if (error && clients.length === 0) {
    return (
      <PageContainer>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center gap-2">
            Failed to load clients: {error}
            <Button variant="link" size="sm" onClick={() => fetchClients()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Clients</h1>
          <p className="text-muted-foreground">Manage your clients and their email infrastructure</p>
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
          description="Get started by adding your first client to manage their email infrastructure."
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
