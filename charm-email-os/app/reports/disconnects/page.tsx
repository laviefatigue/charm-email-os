'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { reportsApi } from '@/lib/reports-api';
import type { DisconnectRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

export default function DisconnectsPage() {
  const [data, setData] = useState<ReportEnvelope<DisconnectRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [attentionOnly, setAttentionOnly] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getDisconnects(attentionOnly)
      .then(setData)
      .finally(() => setIsLoading(false));
  }, [attentionOnly]);

  const columns: ReportColumn<DisconnectRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    { key: 'email_address', label: 'Email' },
    { key: 'esp', label: 'ESP' },
    {
      key: 'disconnected_at',
      label: 'Disconnected',
      render: (r) => (r.disconnected_at ? new Date(r.disconnected_at).toLocaleString() : null),
    },
    {
      key: 'hours_disconnected',
      label: 'Hours',
      align: 'right',
      render: (r) => (r.hours_disconnected != null ? r.hours_disconnected.toFixed(1) : null),
    },
    {
      key: 'needs_attention',
      label: 'Attention',
      render: (r) =>
        r.needs_attention ? (
          <Badge variant="destructive">Past threshold</Badge>
        ) : (
          <Badge variant="secondary">Within threshold</Badge>
        ),
    },
    { key: 'pool_status', label: 'Pool' },
    { key: 'connection_status', label: 'Status' },
    { key: 'total_sends_7d', label: 'Sends 7d', align: 'right' },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Disconnects</h2>
          <p className="text-sm text-muted-foreground">
            Live inboxes with <code className="font-mono text-xs">status != Connected</code>.
            ESP-aware thresholds: Microsoft 48h (IMAP blips are transient),
            Google/other 24h. Sorted oldest disconnect first within each workspace.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              id="attention-only"
              checked={attentionOnly}
              onCheckedChange={setAttentionOnly}
            />
            <Label htmlFor="attention-only" className="text-sm">
              Past threshold only
            </Label>
          </div>
          <DownloadCSVButton
            url={reportsApi.csvUrl('disconnects', { attention_only: String(attentionOnly) })}
            filename={`disconnects-${attentionOnly ? 'needs-attention' : 'all'}.csv`}
          />
        </div>
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
        emptyMessage="No disconnected inboxes."
        groupBy="workspace_name"
        defaultSortKey="disconnected_at"
        defaultSortDirection="asc"
      />
    </div>
  );
}
