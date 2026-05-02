'use client';

import { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { reportsApi } from '@/lib/reports-api';
import type { CancelCandidateRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

export default function CancelCandidatesPage() {
  const [data, setData] = useState<ReportEnvelope<CancelCandidateRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [eligibleOnly, setEligibleOnly] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getCancelCandidates()
      .then(setData)
      .finally(() => setIsLoading(false));
  }, []);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    return eligibleOnly ? data.rows.filter((r) => r.recency_eligible) : data.rows;
  }, [data, eligibleOnly]);

  const columns: ReportColumn<CancelCandidateRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    {
      key: 'recency_eligible',
      label: 'Eligible',
      render: (r) =>
        r.recency_eligible ? (
          <Badge variant="destructive">≥14d clean</Badge>
        ) : (
          <Badge variant="secondary">settling</Badge>
        ),
    },
    { key: 'total_inboxes', label: 'Total', align: 'right' },
    { key: 'dead_inboxes', label: 'Dead', align: 'right' },
    { key: 'dead_connected', label: 'Dead/Conn', align: 'right' },
    { key: 'dead_disconnected', label: 'Dead/Discon', align: 'right' },
    { key: 'live_connected', label: 'Live/Conn', align: 'right' },
    { key: 'live_disconnected', label: 'Live/Discon', align: 'right' },
    {
      key: 'most_recent_kill',
      label: 'Last Kill',
      render: (r) => (r.most_recent_kill ? new Date(r.most_recent_kill).toLocaleDateString() : null),
    },
    {
      key: 'audit_date',
      label: 'Audit',
      render: (r) => new Date(r.audit_date).toLocaleDateString(),
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Subscription Cancel Candidates</h2>
          <p className="text-sm text-muted-foreground">
            Domains where every active inbox is dead. <Badge variant="destructive">≥14d clean</Badge>{' '}
            domains have been all-dead long enough to cancel the Hypertide
            subscription; <Badge variant="secondary">settling</Badge> domains
            had a kill within the reuse window. Per ADR-009, never auto-cancel.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              id="eligible-only"
              checked={eligibleOnly}
              onCheckedChange={setEligibleOnly}
            />
            <Label htmlFor="eligible-only" className="text-sm">
              Eligible only
            </Label>
          </div>
          <DownloadCSVButton
            url={reportsApi.csvUrl('cancel-candidates')}
            filename="cancel-candidates.csv"
          />
        </div>
      </header>
      {data && (
        <p className="text-xs text-muted-foreground">
          showing {filteredRows.length} of {data.row_count} candidate
          {data.row_count === 1 ? '' : 's'} · generated{' '}
          {new Date(data.generated_at).toLocaleString()}
        </p>
      )}
      <ReportTable
        columns={columns}
        rows={filteredRows}
        isLoading={isLoading}
        emptyMessage="No cancel candidates."
        groupBy="workspace_name"
        defaultSortKey="most_recent_kill"
        defaultSortDirection="asc"
      />
    </div>
  );
}
