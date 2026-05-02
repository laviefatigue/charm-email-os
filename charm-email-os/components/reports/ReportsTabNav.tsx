'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  PlugZap,
  Skull,
  Recycle,
  Receipt,
  ShieldAlert,
  Hourglass,
  BarChart3,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const tabs = [
  { name: 'Disconnects',         href: '/reports/disconnects',        icon: PlugZap },
  { name: 'Kills',               href: '/reports/kills',              icon: Skull },
  { name: 'Domains to Rotate',   href: '/reports/rotation',           icon: Recycle },
  { name: 'Cancel Candidates',   href: '/reports/cancel-candidates',  icon: Receipt },
  { name: 'Quarantined',         href: '/reports/quarantined',        icon: ShieldAlert },
  { name: 'Stuck in Incubation', href: '/reports/incubation-stuck',   icon: Hourglass },
  { name: 'Capacity',            href: '/reports/capacity',           icon: BarChart3 },
];

export function ReportsTabNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto border-b px-6">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href || pathname.startsWith(tab.href + '/');
        const Icon = tab.icon;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              'flex items-center gap-2 border-b-2 px-3 py-3 text-sm font-medium whitespace-nowrap transition-colors',
              isActive
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="h-4 w-4" />
            {tab.name}
          </Link>
        );
      })}
    </nav>
  );
}
