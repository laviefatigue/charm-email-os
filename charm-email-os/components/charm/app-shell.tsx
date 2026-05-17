/**
 * AppShell — path-aware sidebar switcher.
 * Renders VillageSidebar for redesign routes (/, /workspaces/*, /recommendations,
 * /activity, /settings). Falls back to legacy Sidebar for everything else
 * (/clients/*, /reports/*, /infrastructure/*).
 *
 * Lets the redesign coexist with legacy routes without restructuring.
 */
"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { VillageSidebar } from "./village-sidebar";
import { Sidebar as LegacySidebar } from "@/components/layout";

const REDESIGN_PATTERNS: RegExp[] = [
  /^\/$/,
  /^\/workspaces(\/|$)/,
  /^\/tasks(\/|$)/,
  /^\/agents(\/|$)/,
  /^\/recommendations(\/|$)/,
  /^\/activity(\/|$)/,
  /^\/settings(\/|$)/,
];

function isRedesignRoute(pathname: string): boolean {
  return REDESIGN_PATTERNS.some((re) => re.test(pathname));
}

export interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const village = isRedesignRoute(pathname);

  return (
    <div className="flex h-screen bg-background">
      {village ? <VillageSidebar /> : <LegacySidebar />}
      <main className="flex-1 flex flex-col overflow-auto">{children}</main>
    </div>
  );
}
