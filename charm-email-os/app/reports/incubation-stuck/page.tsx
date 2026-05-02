'use client';

import { useEffect, useState } from 'react';
import { reportsApi } from '@/lib/reports-api';
import type { IncubationStuckRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

export default function IncubationStuckPage() {
  const [data, setData] = useState<ReportEnvelope<IncubationStuckRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getIncubationStuck(14)
      .then(setData)
      .finally(() => setIsLoading(false));
  }, []);

  const columns: ReportColumn<IncubationStuckRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    { key: 'email_address', label: 'Email' },
    {
      key: 'calendar_days_in_incubation',
      label: 'Days Stuck',
      align: 'right',
      render: (r) => <span className="font-medium">{r.calendar_days_in_incubation}d</span>,
    },
    { key: 'inventory_lifecycle_status', label: 'Lifecycle' },
    { key: 'inventory_pool_status', label: 'Pool' },
    {
      key: 'warmup_started_at',
      label: 'Warmup Start',
      render: (r) =>
        r.warmup_started_at ? new Date(r.warmup_started_at).toLocaleDateString() : null,
    },
    {
      key: 'created_at',
      label: 'Created',
      render: (r) => new Date(r.created_at).toLocaleDateString(),
    },
    {
      key: 'last_synced_at',
      label: 'Last Synced',
      render: (r) => (r.last_synced_at ? new Date(r.last_synced_at).toLocaleString() : null),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Stuck in Incubation</h2>
          <p className="text-sm text-muted-foreground">
            Inboxes still in <code className="font-mono text-xs">incubating</code>{' '}
            past 14 calendar days. Surfaces silent failures where lifecycle_tag_sync
            stops graduating an inbox. Sorted oldest stuck first within each workspace.
          </p>
        </div>
        <DownloadCSVButton
          url={reportsApi.csvUrl('incubation-stuck', { min_calendar_days: '14' })}
          filename="incubation-stuck.csv"
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
        emptyMessage="No inboxes stuck past 14 days — graduation is healthy."
        groupBy="workspace_name"
        defaultSortKey="calendar_days_in_incubation"
        defaultSortDirection="desc"
      />
    </div>
  );
}
