'use client';

import Link from 'next/link';
import { Building2, Package, Globe, Inbox } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import type { Client } from '@/lib/types';
import { getInitials } from '@/lib/utils';

interface ClientCardProps {
  client: Client;
}

// Compute operational capacity status based on connected inboxes vs package target
function getCapacityStatus(client: Client): {
  dots: ('filled' | 'partial' | 'empty')[];
  label: string;
  color: string;
} {
  const hasWorkspace = !!client.workspaceId;
  const packageTarget = client.packageInboxTarget || 0;
  const connectedCount = client.connectedInboxCount || 0;

  // If no workspace linked, show setup needed
  if (!hasWorkspace) {
    return { dots: ['empty', 'empty', 'empty'], label: 'Needs Setup', color: 'text-gray-400' };
  }

  // If no package configured, show that
  if (packageTarget === 0) {
    return { dots: ['empty', 'empty', 'empty'], label: 'No Package', color: 'text-gray-400' };
  }

  // Calculate capacity percentage
  const capacityPercent = (connectedCount / packageTarget) * 100;

  // 90-100% = Full (green)
  if (capacityPercent >= 90) {
    return { dots: ['filled', 'filled', 'filled'], label: 'Full', color: 'text-green-600' };
  }
  // 80-90% = Medium (amber)
  else if (capacityPercent >= 80) {
    return { dots: ['filled', 'filled', 'empty'], label: 'Medium', color: 'text-amber-600' };
  }
  // Below 80% = Low (red)
  else {
    return { dots: ['filled', 'empty', 'empty'], label: 'Low', color: 'text-red-600' };
  }
}

export function ClientCard({ client }: ClientCardProps) {
  const status = getCapacityStatus(client);
  const primaryDomain = client.onboardingData?.primaryDomain || client.domain || '';

  return (
    <Link href={`/clients/${client.id}`}>
      <Card className="transition-all hover:shadow-md hover:-translate-y-0.5 cursor-pointer border-gray-200 bg-white">
        <CardContent className="p-5">
          {/* Header with icon and name */}
          <div className="flex items-start gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-linear-to-br from-slate-100 to-slate-200 shrink-0">
              <Building2 className="h-5 w-5 text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-base truncate text-gray-900">{client.name}</h3>
              {primaryDomain && (
                <p className="text-sm text-gray-500 truncate">{primaryDomain}</p>
              )}
            </div>
          </div>

          {/* Package info with capacity status */}
          <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Package className="h-4 w-4 text-gray-400" />
                <span className="text-gray-600 font-medium">
                  {client.packageName || 'No Package'}
                </span>
              </div>
              {/* Capacity status indicator */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1">
                  {status.dots.map((dot, i) => (
                    <span
                      key={i}
                      className={`w-2 h-2 rounded-full ${
                        dot === 'filled'
                          ? 'bg-green-500'
                          : dot === 'partial'
                          ? 'bg-amber-500'
                          : 'bg-gray-300'
                      }`}
                    />
                  ))}
                </div>
                <span className={`text-xs font-medium ${status.color}`}>
                  {status.label}
                </span>
              </div>
            </div>
            <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Globe className="h-3 w-3" />
                {client.domainCount || 0} domains
              </span>
              <span className="flex items-center gap-1">
                <Inbox className="h-3 w-3" />
                {client.inboxCount || 0} inboxes
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
