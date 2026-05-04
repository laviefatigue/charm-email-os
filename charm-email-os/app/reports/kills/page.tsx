'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { reportsApi } from '@/lib/reports-api';
import type { KillRow, ReportEnvelope } from '@/lib/types/reports';
import { ReportTable, type ReportColumn } from '@/components/reports/ReportTable';
import { DownloadCSVButton } from '@/components/reports/DownloadCSVButton';

type Window = 'all' | '24h' | '7d' | '30d';

const DOMAIN_KILLING = new Set(['spam_complaint']);

function severityBadge(trigger: string) {
  if (DOMAIN_KILLING.has(trigger) || trigger.startsWith('provider_block_')) {
    return <Badge variant="destructive">domain</Badge>;
  }
  return <Badge variant="secondary">inbox</Badge>;
}

export default function KillsPage() {
  const [windowSize, setWindowSize] = useState<Window>('all');
  const [data, setData] = useState<ReportEnvelope<KillRow> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    reportsApi
      .getKills(windowSize)
      .then(setData)
      .finally(() => setIsLoading(false));
  }, [windowSize]);

  const columns: ReportColumn<KillRow>[] = [
    { key: 'workspace_name', label: 'Workspace' },
    { key: 'domain_name', label: 'Domain' },
    { key: 'email_address', label: 'Email' },
    {
      key: 'kill_trigger',
      label: 'Trigger',
      render: (r) => (
        <span className="inline-flex items-center gap-2">
          {severityBadge(r.kill_trigger)}
          <code className="font-mono text-xs">{r.kill_trigger}</code>
        </span>
      ),
    },
    {
      key: 'killed_at',
      label: 'Killed',
      render: (r) => new Date(r.killed_at).toLocaleString(),
    },
    { key: 'esp', label: 'ESP' },
    { key: 'pool_status_before_kill', label: 'Pool (pre-kill)' },
    { key: 'total_sends_7d', label: 'Sends 7d', align: 'right' },
    { key: 'hard_bounces_24h', label: 'HBounce 24h', align: 'right' },
    {
      key: 'kill_reason',
      label: 'Reason',
      render: (r) =>
        r.kill_reason ? (
          <span className="block max-w-[24rem] truncate font-mono text-xs" title={r.kill_reason}>
            {r.kill_reason}
          </span>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Kills</h2>
          <p className="text-sm text-muted-foreground">
            Per-inbox kill events. <Badge variant="destructive">domain</Badge>{' '}
            triggers compromise the entire domain (spam complaints, provider
            blocks); <Badge variant="secondary">inbox</Badge> triggers are
            single-inbox issues. Sorted most recent first within each workspace.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-md border">
            {(['all', '24h', '7d', '30d'] as Window[]).map((w) => (
              <Button
                key={w}
                size="sm"
                variant={windowSize === w ? 'default' : 'ghost'}
                className="rounded-none first:rounded-l-md last:rounded-r-md border-0"
                onClick={() => setWindowSize(w)}
              >
                {w}
              </Button>
            ))}
          </div>
          <DownloadCSVButton
            url={reportsApi.csvUrl('kills', { window: windowSize })}
            filename={`kills-${windowSize}.csv`}
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
        emptyMessage={windowSize === 'all' ? 'No kills recorded.' : `No kills in the last ${windowSize}.`}
        groupBy="workspace_name"
        defaultSortKey="killed_at"
        defaultSortDirection="desc"
      />
    </div>
  );
}
