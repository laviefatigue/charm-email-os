'use client';

import { ListX, AlertTriangle, Calendar, Building2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ListContaminationSource } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface ListContaminationTrackerProps {
  sources: ListContaminationSource[];
}

export function ListContaminationTracker({ sources }: ListContaminationTrackerProps) {
  const flaggedSources = sources.filter((s) => s.status === 'flagged');
  const quarantinedSources = sources.filter((s) => s.status === 'quarantined');

  // Sort by bounce rate descending
  const sortedSources = [...sources].sort((a, b) => b.bounceRate - a.bounceRate);

  const formatDate = (date: Date) => {
    return new Date(date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const sourceTypeColors: Record<string, { bg: string; text: string }> = {
    enrichment: { bg: 'bg-blue-100', text: 'text-blue-800' },
    scraped: { bg: 'bg-purple-100', text: 'text-purple-800' },
    manual: { bg: 'bg-green-100', text: 'text-green-800' },
    purchased: { bg: 'bg-orange-100', text: 'text-orange-800' },
    unknown: { bg: 'bg-gray-100', text: 'text-gray-800' },
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ListX className="h-5 w-5" />
            List Contamination
          </CardTitle>
          {(flaggedSources.length > 0 || quarantinedSources.length > 0) && (
            <div className="flex items-center gap-2 text-sm">
              {quarantinedSources.length > 0 && (
                <Badge variant="destructive">{quarantinedSources.length} quarantined</Badge>
              )}
              {flaggedSources.length > 0 && (
                <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">
                  {flaggedSources.length} flagged
                </Badge>
              )}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {sources.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <ListX className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="font-medium">List Quality Tracking</p>
            <p className="text-sm mt-1">Lead import data with bounce status tracking not yet configured</p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Header row */}
            <div className="grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground py-2 border-b">
              <div className="col-span-3">List Name</div>
              <div className="col-span-2 text-center">Bounces</div>
              <div className="col-span-2 text-center">Rate</div>
              <div className="col-span-2 text-center">Source</div>
              <div className="col-span-3 text-center">Impact</div>
            </div>

            {/* Source rows */}
            {sortedSources.map((source) => (
              <div
                key={source.id}
                className={cn(
                  'grid grid-cols-12 gap-2 py-3 items-center text-sm border-b last:border-0',
                  source.status === 'quarantined' && 'bg-red-50/50',
                  source.status === 'flagged' && 'bg-yellow-50/50'
                )}
              >
                <div className="col-span-3">
                  <div className="font-medium truncate">{source.listName}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {source.campaignName}
                  </div>
                </div>
                <div className="col-span-2 text-center">
                  <span className="font-medium">{source.bouncedLeads}</span>
                  <span className="text-muted-foreground text-xs"> / {source.totalLeads}</span>
                </div>
                <div
                  className={cn(
                    'col-span-2 text-center font-medium',
                    source.bounceRate > 5 && 'text-red-600',
                    source.bounceRate > 3 && source.bounceRate <= 5 && 'text-orange-600',
                    source.bounceRate > 2 && source.bounceRate <= 3 && 'text-yellow-600'
                  )}
                >
                  {source.bounceRate.toFixed(1)}%
                </div>
                <div className="col-span-2 text-center">
                  <Badge
                    variant="outline"
                    className={cn(
                      sourceTypeColors[source.sourceType]?.bg,
                      sourceTypeColors[source.sourceType]?.text,
                      'capitalize'
                    )}
                  >
                    {source.sourceType}
                  </Badge>
                  {source.sourceProvider && (
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {source.sourceProvider}
                    </div>
                  )}
                </div>
                <div className="col-span-3 text-center">
                  <div className="flex items-center justify-center gap-3 text-xs">
                    {source.inboxesAffected > 0 && (
                      <span className="text-red-600">
                        {source.inboxesAffected} inboxes
                      </span>
                    )}
                    {source.domainsAffected > 0 && (
                      <span className="text-red-600">
                        {source.domainsAffected} domains
                      </span>
                    )}
                    {source.inboxesAffected === 0 && source.domainsAffected === 0 && (
                      <span className="text-muted-foreground">No impact</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
