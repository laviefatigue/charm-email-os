'use client';

import { Globe, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DomainHealthCard } from './DomainHealthCard';
import type { DomainHealthMetrics } from '@/lib/types/health';

interface DomainHealthGridProps {
  domains: DomainHealthMetrics[];
  onDomainClick?: (domainId: string) => void;
}

export function DomainHealthGrid({ domains, onDomainClick }: DomainHealthGridProps) {
  const liveDomains = domains.filter((d) => d.state === 'live');
  const flaggedDomains = domains.filter((d) => d.state === 'flagged');
  const deadDomains = domains.filter((d) => d.state === 'dead');

  // Sort: flagged first (need attention), then dead, then live
  const sortedDomains = [...flaggedDomains, ...deadDomains, ...liveDomains];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Domain Health
          </CardTitle>
          <div className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1 text-green-600">
              <CheckCircle className="h-4 w-4" />
              {liveDomains.length} live
            </span>
            {flaggedDomains.length > 0 && (
              <span className="flex items-center gap-1 text-yellow-600">
                <AlertTriangle className="h-4 w-4" />
                {flaggedDomains.length} flagged
              </span>
            )}
            {deadDomains.length > 0 && (
              <span className="flex items-center gap-1 text-red-600">
                <XCircle className="h-4 w-4" />
                {deadDomains.length} dead
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {domains.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Globe className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="font-medium">No domains found</p>
            <p className="text-sm mt-1">Add domains in the Inboxes tab to monitor health</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {sortedDomains.map((domain) => (
              <DomainHealthCard
                key={domain.domainId}
                domain={domain}
                onClick={onDomainClick ? () => onDomainClick(domain.domainId) : undefined}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
