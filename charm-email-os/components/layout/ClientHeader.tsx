'use client';

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import type { Client } from '@/lib/types';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { getInitials } from '@/lib/utils';

interface ClientHeaderProps {
  client: Client;
}

export function ClientHeader({ client }: ClientHeaderProps) {
  return (
    <div className="flex items-center gap-4 border-b bg-background px-6 py-4">
      <Link
        href="/clients"
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        <span>Back to Clients</span>
      </Link>

      <div className="h-6 w-px bg-border" />

      <div className="flex items-center gap-3">
        <Avatar className="h-10 w-10">
          <AvatarFallback className="bg-primary/10 text-primary text-sm font-medium">
            {getInitials(client.name)}
          </AvatarFallback>
        </Avatar>
        <div>
          <h1 className="text-lg font-semibold">{client.name}</h1>
          <p className="text-sm text-muted-foreground">{client.domain}</p>
        </div>
      </div>
    </div>
  );
}
