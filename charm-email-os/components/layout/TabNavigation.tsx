'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Server, Building2, ArrowLeft } from 'lucide-react';

interface TabNavigationProps {
  clientId: string;
}

// Simplified tabs for Domain Manager app
const tabs = [
  { name: 'Profile', href: '', icon: Building2 },
  { name: 'Infrastructure', href: 'infrastructure', icon: Server },
];

export function TabNavigation({ clientId }: TabNavigationProps) {
  const pathname = usePathname();
  const baseUrl = `/clients/${clientId}`;

  return (
    <div className="border-b bg-background mb-6">
      <nav className="flex items-center gap-1 px-6">
        {/* Back to Clients */}
        <Link
          href="/clients"
          className="flex items-center gap-2 px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors border-b-2 border-transparent"
        >
          <ArrowLeft className="h-4 w-4" />
          Clients
        </Link>

        <div className="w-px h-6 bg-border mx-2" />

        {/* Page tabs */}
        {tabs.map((tab) => {
          const href = tab.href ? `${baseUrl}/${tab.href}` : baseUrl;
          const isActive = tab.href
            ? pathname.startsWith(href)
            : pathname === baseUrl;

          return (
            <Link
              key={tab.name}
              href={href}
              className={cn(
                'flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted'
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.name}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
