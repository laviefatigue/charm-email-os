'use client';

import { Badge } from '@/components/ui/badge';
import { Lightbulb, AlertTriangle, Info, Database, FlaskConical, StopCircle } from 'lucide-react';
import type { StrategyNotes, StrategyCallout, DataEnrichment } from '@/lib/types';
import { CALLOUT_COLORS } from '@/lib/types';
import { cn } from '@/lib/utils';

interface StrategyNotesSectionProps {
  notes: StrategyNotes;
  className?: string;
}

function CalloutCard({ callout }: { callout: StrategyCallout }) {
  const colors = CALLOUT_COLORS[callout.type] || CALLOUT_COLORS.info;

  const icons = {
    recommendation: Lightbulb,
    warning: AlertTriangle,
    info: Info,
  };
  const Icon = icons[callout.type] || Info;

  return (
    <div className={cn(
      'flex items-start gap-3 p-4 rounded-lg border-l-4',
      colors.bg,
      colors.border
    )}>
      <Icon className={cn('h-5 w-5 shrink-0 mt-0.5', colors.icon)} />
      <p className="text-sm">{callout.text}</p>
    </div>
  );
}

function EnrichmentTable({ enrichments }: { enrichments: DataEnrichment[] }) {
  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-muted/50">
          <tr>
            <th className="text-left text-xs font-medium text-muted-foreground p-3">
              Variable
            </th>
            <th className="text-left text-xs font-medium text-muted-foreground p-3">
              Data Source
            </th>
          </tr>
        </thead>
        <tbody>
          {enrichments.map((enrichment, idx) => (
            <tr key={idx} className="border-b last:border-0">
              <td className="py-2.5 px-3">
                <code className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded text-sm font-mono">
                  {`{{${enrichment.variable}}}`}
                </code>
              </td>
              <td className="py-2.5 px-3 text-sm text-muted-foreground">
                {enrichment.source}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StrategyNotesSection({ notes, className }: StrategyNotesSectionProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {/* Callouts */}
      {notes.callouts && notes.callouts.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Lightbulb className="h-4 w-4" />
            Strategic Recommendations
          </h4>
          <div className="space-y-3">
            {notes.callouts.map((callout, idx) => (
              <CalloutCard key={idx} callout={callout} />
            ))}
          </div>
        </div>
      )}

      {/* Data Enrichment */}
      {notes.dataEnrichment && notes.dataEnrichment.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Database className="h-4 w-4" />
            Data Enrichment Sources
          </h4>
          <EnrichmentTable enrichments={notes.dataEnrichment} />
        </div>
      )}

      {/* A/B Testing Recommendations */}
      {notes.abTesting && notes.abTesting.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            A/B Testing Recommendations
          </h4>
          <ul className="space-y-2">
            {notes.abTesting.map((test, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="shrink-0 mt-0.5">Test {idx + 1}</Badge>
                <span>{test}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* After Sequence Note */}
      {notes.afterSequenceNote && (
        <div className="flex items-start gap-3 p-4 rounded-lg border-l-4 bg-slate-50 border-slate-300">
          <StopCircle className="h-5 w-5 shrink-0 mt-0.5 text-slate-600" />
          <div>
            <p className="text-sm font-medium text-slate-700 mb-1">Post-Sequence Guidance</p>
            <p className="text-sm text-slate-600">{notes.afterSequenceNote}</p>
          </div>
        </div>
      )}
    </div>
  );
}
