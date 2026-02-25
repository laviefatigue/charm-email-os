'use client';

import Link from 'next/link';
import { Building2, Inbox, Megaphone } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import type { Client } from '@/lib/types';
import { getInitials } from '@/lib/utils';

interface ClientCardProps {
  client: Client;
}

export function ClientCard({ client }: ClientCardProps) {
  return (
    <Link href={`/clients/${client.id}`}>
      <Card className="transition-all hover:shadow-md hover:-translate-y-0.5 cursor-pointer">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <Avatar className="h-12 w-12">
              <AvatarFallback className="bg-primary/10 text-primary font-medium">
                {getInitials(client.name)}
              </AvatarFallback>
            </Avatar>

            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-lg truncate">{client.name}</h3>
              {client.workspaceName && (
                <p className="text-sm text-muted-foreground flex items-center gap-1">
                  <Building2 className="h-3 w-3" />
                  {client.workspaceName}
                </p>
              )}

              <div className="mt-3 flex items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Inbox className="h-4 w-4" />
                  {client.inboxCount || 0} inboxes
                </span>
                <span className="flex items-center gap-1">
                  <Megaphone className="h-4 w-4" />
                  {client.campaignCount || 0} campaigns
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
