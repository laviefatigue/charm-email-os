'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { reportsApi } from '@/lib/reports-api';
import type { CapacityRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

function healthBadge(pct: number | null) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  let variant: 'destructive' | 'default' | 'secondary' = 'secondary';
  if (pct < 50) variant = 'destructive';
  else if (pct < 70) variant = 'default';
  return <Badge variant={variant}>{pct}%</Badge>;
}

export default function CapacityPage() {
  const [data, setData] = useState<ReportEnvelope<CapacityRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getCapacity()
      .then(setData)
      .finally(() => setIsLoading(false));
  }, []);

  const columns: ReportColumn<CapacityRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'health_pct', label: 'Health', render: (r) => healthBadge(r.health_pct), align: 'right' },
    { key: 'total_inboxes', label: 'Total', align: 'right' },
    { key: 'live_connected', label: 'Live/Conn', align: 'right' },
    { key: 'live_disconnected', label: 'Live/Discon', align: 'right' },
    { key: 'dead', label: 'Dead', align: 'right' },
    {
      key: 'spam_compromised_domains',
      label: 'Spam Domains',
      align: 'right',
      render: (r) =>
        r.spam_compromised_domains > 0 ? (
          <Badge variant="destructive">{r.spam_compromised_domains}</Badge>
        ) : (
          <span className="text-muted-foreground">0</span>
        ),
    },
    { key: 'target_live', label: 'Target', align: 'right' },
    {
      key: 'most_recent_event',
      label: 'Last Event',
      render: (r) => (r.most_recent_event ? new Date(r.most_recent_event).toLocaleString() : null),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Capacity</h2>
          <p className="text-sm text-muted-foreground">
            Per-workspace capacity health: live-connected count vs total, dead
            count, spam-compromised domain count, and target_live override
            (when set). Sorted by workspace name.
          </p>
        </div>
        <DownloadCSVButton
          url={reportsApi.csvUrl('capacity')}
          filename="capacity.csv"
        />
      </header>
      {data && (
        <p className="text-xs text-muted-foreground">
          {data.row_count} workspace{data.row_count === 1 ? '' : 's'} · generated{' '}
          {new Date(data.generated_at).toLocaleString()}
        </p>
      )}
      <ReportTable
        columns={columns}
        rows={data?.rows ?? []}
        isLoading={isLoading}
        emptyMessage="No active workspaces with inboxes."
        defaultSortKey="health_pct"
        defaultSortDirection="asc"
      />
    </div>
  );
}
