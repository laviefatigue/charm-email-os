'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { TableCell, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { StatusBadge } from '@/components/shared';
import type { Campaign } from '@/lib/types';

interface ApprovedCampaignRowProps {
  campaign: Campaign;
  clientId: string;
}

export function ApprovedCampaignRow({ campaign, clientId }: ApprovedCampaignRowProps) {
  return (
    <TableRow>
      <TableCell className="font-medium">{campaign.name}</TableCell>
      <TableCell>
        <Badge variant="outline">{campaign.industry}</Badge>
      </TableCell>
      <TableCell>
        <Badge variant="secondary">{campaign.segment}</Badge>
      </TableCell>
      <TableCell>
        <StatusBadge status={campaign.status} />
      </TableCell>
      <TableCell className="text-right">
        <Link href={`/clients/${clientId}/leads`}>
          <Button size="sm" variant="ghost">
            Configure in Leads
            <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </Link>
      </TableCell>
    </TableRow>
  );
}
