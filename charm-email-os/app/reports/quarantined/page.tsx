'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { reportsApi } from '@/lib/reports-api';
import type { QuarantinedRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

export default function QuarantinedPage() {
  const [data, setData] = useState<ReportEnvelope<QuarantinedRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getQuarantined()
      .then(setData)
      .finally(() => setIsLoading(false));
  }, []);

  const columns: ReportColumn<QuarantinedRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    { key: 'email_address', label: 'Email' },
    {
      key: 'quarantine_reason',
      label: 'Reason',
      render: (r) =>
        r.quarantine_reason ? (
          <code className="font-mono text-xs">{r.quarantine_reason}</code>
        ) : null,
    },
    { key: 'inbox_state', label: 'State' },
    { key: 'connection_status', label: 'Connection' },
    {
      key: 'inventory_pool_status',
      label: 'Pool',
      render: (r) =>
        r.inventory_pool_status ? (
          <code className="font-mono text-xs">{r.inventory_pool_status}</code>
        ) : (
          <Badge variant="secondary">null (locked)</Badge>
        ),
    },
    {
      key: 'updated_at',
      label: 'Updated',
      render: (r) => new Date(r.updated_at).toLocaleString(),
    },
    {
      key: 'created_at',
      label: 'Created',
      render: (r) => new Date(r.created_at).toLocaleDateString(),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Quarantined Inboxes</h2>
          <p className="text-sm text-muted-foreground">
            Inboxes locked out by the cross-workspace integrity firewall (HR-1).
            Pool status is forced NULL while quarantined; the CHECK constraint
            in migration 103 enforces this structurally. Sorted by most recent
            update within each workspace. <strong>0 fleet-wide is the
            expected steady state.</strong>
          </p>
        </div>
        <DownloadCSVButton
          url={reportsApi.csvUrl('quarantined')}
          filename="quarantined.csv"
        />
      </header>
      {data && (
        <p className="text-xs text-muted-foreground">
          {data.row_count} row{data.row_count === 1 ? '' : 's'} · generated{' '}
          {new Date(data.generated_at).toLocaleString()}
        </p>
      )}
      <ReportTable
        columns={columns}
        rows={data?.rows ?? []}
        isLoading={isLoading}
        emptyMessage="No quarantined inboxes — firewall steady state is clean."
        groupBy="workspace_name"
        defaultSortKey="updated_at"
        defaultSortDirection="desc"
      />
    </div>
  );
}
