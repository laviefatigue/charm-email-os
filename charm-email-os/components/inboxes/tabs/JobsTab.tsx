'use client';

import { PurchaseJobsTable } from '@/components/purchasing';

interface JobsTabProps {
  clientId: string;
  onJobRetried: () => void;
}

export function JobsTab({ clientId, onJobRetried }: JobsTabProps) {
  return (
    <PurchaseJobsTable
      clientId={clientId}
      onJobRetried={onJobRetried}
    />
  );
}
