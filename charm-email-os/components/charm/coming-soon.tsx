/**
 * ComingSoon — placeholder panel for sub-nav surfaces not yet built.
 * Used in stub pages for Domains, Inboxes, Pending Gates, Routines, Context,
 * Integrations, Costs, Settings (per design-app Phase 0 scope).
 */
import * as React from "react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ComingSoonProps {
  title: string;
  description?: string;
  cta?: React.ReactNode;
  className?: string;
}

export function ComingSoon({ title, description, cta, className }: ComingSoonProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center gap-3 p-12 rounded-xl",
        "border-[1.5px] border-dashed border-border bg-muted/30",
        className
      )}
    >
      <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/20 text-copper border-[1.5px] border-copper">
        <Sparkles className="h-6 w-6" aria-hidden="true" />
      </span>
      <div>
        <h3 className="text-xl text-foreground">{title}</h3>
        {description && (
          <p className="mt-1 text-sm text-ink-soft max-w-md">{description}</p>
        )}
      </div>
      {cta && <div className="mt-1">{cta}</div>}
    </div>
  );
}
