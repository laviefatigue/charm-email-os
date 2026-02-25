'use client';

import { Users, Send, MessageSquare, Target } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { formatNumber } from '@/lib/utils';
import type { Campaign } from '@/lib/types';

interface StatsRowProps {
  campaign: Campaign;
}

const stats = [
  { key: 'uploaded', label: 'Leads Uploaded', icon: Users, getValue: (c: Campaign) => c.leadsTotal },
  { key: 'contacted', label: 'Leads Contacted', icon: Send, getValue: (c: Campaign) => c.leadsContacted },
  { key: 'replies', label: 'Replies', icon: MessageSquare, getValue: (c: Campaign) => c.repliesCount },
  { key: 'capacity', label: 'Capacity', icon: Target, getValue: (c: Campaign) => `${c.leadsTotal}/${c.leadsCapacity}` },
];

export function StatsRow({ campaign }: StatsRowProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4">
      {stats.map((stat) => (
        <Card key={stat.key}>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                <stat.icon className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="text-xl font-semibold">
                  {typeof stat.getValue(campaign) === 'number'
                    ? formatNumber(stat.getValue(campaign) as number)
                    : stat.getValue(campaign)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
