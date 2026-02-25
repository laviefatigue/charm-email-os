'use client';

import { Badge } from '@/components/ui/badge';
import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import type { QAScoring, QADimension } from '@/lib/types';
import { VERDICT_COLORS } from '@/lib/types';
import { cn } from '@/lib/utils';

interface QAScoringCardProps {
  scoring: QAScoring;
  className?: string;
}

function ScoreBadge({ score, max }: { score: string | number; max?: number }) {
  // Handle both formats: "24/25" string or separate score/max numbers
  let current: number;
  let maxValue: number;
  let displayScore: string;

  if (typeof score === 'string' && score.includes('/')) {
    // Parse "24/25" format
    [current, maxValue] = score.split('/').map(Number);
    displayScore = score;
  } else {
    // Use separate score and max fields
    current = typeof score === 'number' ? score : parseInt(score, 10);
    maxValue = max || 25;
    displayScore = `${current}/${maxValue}`;
  }

  const percentage = maxValue ? (current / maxValue) * 100 : 0;

  return (
    <span className={cn(
      'font-mono text-sm font-semibold px-2 py-0.5 rounded',
      percentage >= 90 ? 'bg-emerald-100 text-emerald-700' :
      percentage >= 70 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
    )}>
      {displayScore}
    </span>
  );
}

function DimensionRow({ dimension }: { dimension: QADimension }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-3 pr-4 font-medium">{dimension.name}</td>
      <td className="py-3 px-4 text-center">
        <ScoreBadge score={dimension.score} max={dimension.max} />
      </td>
      <td className="py-3 pl-4 text-sm text-muted-foreground">{dimension.notes}</td>
    </tr>
  );
}

export function QAScoringCard({ scoring, className }: QAScoringCardProps) {
  const verdictColors = VERDICT_COLORS[scoring.verdict] || {
    bg: 'bg-gray-50',
    text: 'text-gray-700',
    border: 'border-gray-200',
  };

  // Determine verdict icon
  const VerdictIcon = scoring.overallScore >= 90 ? CheckCircle :
                      scoring.overallScore >= 75 ? AlertTriangle : XCircle;

  return (
    <div className={cn('space-y-6', className)}>
      {/* Overall Score & Verdict */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-6">
          {/* Large Score Display */}
          <div className="text-center">
            <div className={cn(
              'text-5xl font-bold',
              scoring.overallScore >= 90 ? 'text-emerald-600' :
              scoring.overallScore >= 75 ? 'text-amber-600' : 'text-red-600'
            )}>
              {scoring.overallScore}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Overall Score</div>
          </div>

          {/* Verdict Badge */}
          <div className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg border',
            verdictColors.bg,
            verdictColors.border
          )}>
            <VerdictIcon className={cn('h-5 w-5', verdictColors.text)} />
            <span className={cn('font-semibold', verdictColors.text)}>
              {scoring.verdict}
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            90+ Ship it
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            75-89 One more pass
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            &lt;75 Start over
          </div>
        </div>
      </div>

      {/* Dimension Breakdown */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left text-xs font-medium text-muted-foreground p-3">
                Dimension
              </th>
              <th className="text-center text-xs font-medium text-muted-foreground p-3 w-24">
                Score
              </th>
              <th className="text-left text-xs font-medium text-muted-foreground p-3">
                Notes
              </th>
            </tr>
          </thead>
          <tbody>
            {scoring.dimensions.map((dimension, idx) => (
              <DimensionRow key={idx} dimension={dimension} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
