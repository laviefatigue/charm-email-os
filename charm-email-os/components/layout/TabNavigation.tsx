'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Inbox, Lightbulb, Users, HeartPulse, Building2 } from 'lucide-react';

interface TabNavigationProps {
  clientId: string;
}

const tabs = [
  { name: 'Profile', href: 'profile', icon: Building2 },
  { name: 'Domains / Inboxes', href: 'inboxes', icon: Inbox },
  { name: 'Strategy', href: 'strategy', icon: Lightbulb },
  { name: 'Leads', href: 'leads', icon: Users },
  { name: 'Health', href: 'health', icon: HeartPulse },
];

export function TabNavigation({ clientId }: TabNavigationProps) {
  const pathname = usePathname();

  return (
    <div className="border-b bg-background">
      <nav className="flex gap-1 px-6">
        {tabs.map((tab) => {
          const href = `/clients/${clientId}/${tab.href}`;
          const isActive = pathname === href;

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
