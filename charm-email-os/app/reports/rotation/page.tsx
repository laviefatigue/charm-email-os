'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { reportsApi } from '@/lib/reports-api';
import type { ReportEnvelope, RotationRow } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

const REASON_VARIANT: Record<RotationRow['rotation_reason'], 'destructive' | 'default' | 'secondary'> = {
  spam_compromised: 'destructive',
  provider_blocked: 'destructive',
  all_dead: 'default',
  high_death_rate: 'default',
  monitor: 'secondary',
};

export default function RotationPage() {
  const [data, setData] = useState<ReportEnvelope<RotationRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getRotation()
      .then(setData)
      .finally(() => setIsLoading(false));
  }, []);

  const columns: ReportColumn<RotationRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    {
      key: 'rotation_reason',
      label: 'Reason',
      render: (r) => (
        <Badge variant={REASON_VARIANT[r.rotation_reason]}>
          {r.rotation_reason.replace(/_/g, ' ')}
        </Badge>
      ),
    },
    { key: 'total_inboxes', label: 'Total', align: 'right' },
    { key: 'dead_inboxes', label: 'Dead', align: 'right' },
    {
      key: 'death_rate_pct',
      label: 'Death %',
      align: 'right',
      render: (r) => (r.death_rate_pct != null ? `${r.death_rate_pct}%` : null),
    },
    { key: 'spam_complaints', label: 'Spam', align: 'right' },
    { key: 'provider_blocks', label: 'Blocks', align: 'right' },
    {
      key: 'most_recent_kill',
      label: 'Last Kill',
      render: (r) => (r.most_recent_kill ? new Date(r.most_recent_kill).toLocaleString() : null),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Domains to Rotate</h2>
          <p className="text-sm text-muted-foreground">
            Domains with spam complaints, provider blocks, full death, or ≥80%
            death rate (with at least 5 inboxes). Sorted most recent kill first
            within each workspace.
          </p>
        </div>
        <DownloadCSVButton
          url={reportsApi.csvUrl('rotation')}
          filename="rotation.csv"
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
        emptyMessage="No domains currently flagged for rotation."
        groupBy="workspace_name"
        defaultSortKey="most_recent_kill"
        defaultSortDirection="desc"
      />
    </div>
  );
}
