/**
 * PageHeader — shared header pattern for redesign pages.
 * Title + optional kicker + optional subtitle + optional right-side actions.
 *
 * Tokens: --foreground, --ink-soft, --border
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  /** Small uppercase label above the title (e.g. workspace slug, breadcrumb). */
  kicker?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex items-end justify-between gap-6 pb-6 mb-8 border-b border-border",
        className
      )}
    >
      <div className="min-w-0 space-y-1">
        {kicker && (
          <div className="text-xs font-medium uppercase tracking-wider text-ink-soft">
            {kicker}
          </div>
        )}
        <h1 className="text-4xl text-foreground truncate">{title}</h1>
        {subtitle && (
          <p className="text-sm text-ink-soft max-w-2xl">{subtitle}</p>
        )}
      </div>
      {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
    </header>
  );
}
