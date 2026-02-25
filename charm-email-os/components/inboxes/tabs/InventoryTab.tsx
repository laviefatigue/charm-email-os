'use client';

import { useState } from 'react';
import { Plus, Globe, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { EmptyState } from '@/components/shared';
import {
  DomainForm,
  InboxForm,
  DomainEditModal,
  InboxEditModal,
  DomainInboxTree,
} from '@/components/inboxes';
import type { Domain, Inbox } from '@/lib/types';

interface InventoryTabProps {
  clientId: string;
  inventoryDomains: Domain[];
  approvedDomains: Domain[];
  allDomains: Domain[];
  allInboxes: Inbox[];
  loadingDomainIds: Set<string>;
  onExpandDomain: (domainId: string) => void;
}

export function InventoryTab({
  clientId,
  inventoryDomains,
  approvedDomains,
  allDomains,
  allInboxes,
  loadingDomainIds,
  onExpandDomain,
}: InventoryTabProps) {
  // Local state for forms and edit modals
  const [showDomainForm, setShowDomainForm] = useState(false);
  const [showInboxForm, setShowInboxForm] = useState(false);
  const [editingDomain, setEditingDomain] = useState<Domain | null>(null);
  const [editingInbox, setEditingInbox] = useState<Inbox | null>(null);

  return (
    <>
      {/* Empty State for Inventory */}
      {inventoryDomains.length === 0 && (
        <Alert className="mb-6">
          <Sparkles className="h-4 w-4" />
          <AlertDescription>
            <strong>No active domains yet.</strong> Go to the &quot;Procurement&quot; tab to generate
            domain suggestions, check pricing, and purchase domains.
          </AlertDescription>
        </Alert>
      )}

      {/* Domain/Inbox Tree View */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Globe className="h-4 w-4" />
                Domains & Inboxes
              </CardTitle>
              <CardDescription className="mt-1">
                Click a domain to expand and see its inboxes
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowInboxForm(true)}
                disabled={approvedDomains.length === 0}
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Inbox
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {inventoryDomains.length === 0 ? (
            <EmptyState
              icon={Globe}
              title="No active domains"
              description="Go to the 'Procurement' tab to generate and purchase domains."
            />
          ) : (
            <DomainInboxTree
              domains={inventoryDomains}
              inboxes={allInboxes}
              onExpandDomain={onExpandDomain}
              loadingDomainIds={loadingDomainIds}
            />
          )}
        </CardContent>
      </Card>

      {/* Forms */}
      <DomainForm
        clientId={clientId}
        open={showDomainForm}
        onOpenChange={setShowDomainForm}
      />
      <InboxForm
        clientId={clientId}
        open={showInboxForm}
        onOpenChange={setShowInboxForm}
      />

      {/* Edit Modals */}
      <DomainEditModal
        domain={editingDomain}
        open={editingDomain !== null}
        onOpenChange={(open) => !open && setEditingDomain(null)}
      />
      <InboxEditModal
        inbox={editingInbox}
        domains={allDomains}
        open={editingInbox !== null}
        onOpenChange={(open) => !open && setEditingInbox(null)}
      />
    </>
  );
}
