'use client';

import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Calendar, Target, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { RequestRevisionButton } from './RequestRevisionButton';

interface CycleHeaderProps {
  cycleNumber: number;
  startDate: Date;
  endDate: Date;
  status: 'draft' | 'planning' | 'planned' | 'active' | 'completed';
  strategicFocus?: string;
  targetOutcome?: string;
  className?: string;
  onRequestRevision?: () => void;
  isSubmitting?: boolean;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  draft: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Draft' },
  planning: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Planning' },
  planned: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Planned' },
  active: { bg: 'bg-green-100', text: 'text-green-800', label: 'Active' },
  completed: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Completed' },
};

export function CycleHeader({
  cycleNumber,
  startDate,
  endDate,
  status,
  strategicFocus,
  targetOutcome,
  className,
  onRequestRevision,
  isSubmitting,
}: CycleHeaderProps) {
  const statusStyle = STATUS_STYLES[status] || STATUS_STYLES.draft;

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xl flex items-center gap-3">
            <span>Cycle {cycleNumber}</span>
            <Badge className={cn(statusStyle.bg, statusStyle.text, 'font-medium')}>
              {statusStyle.label}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-3">
            {onRequestRevision && (
              <RequestRevisionButton
                onClick={onRequestRevision}
                isSubmitting={isSubmitting}
                tooltip="Request revision for strategic focus and target outcome"
              />
            )}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Calendar className="h-4 w-4" />
              <span>
                {format(new Date(startDate), 'MMM d')} - {format(new Date(endDate), 'MMM d, yyyy')}
              </span>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="grid gap-4 md:grid-cols-2">
          {strategicFocus && (
            <div className="flex items-start gap-2">
              <Target className="h-4 w-4 mt-0.5 text-blue-600" />
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Strategic Focus</p>
                <p className="text-sm">{strategicFocus}</p>
              </div>
            </div>
          )}
          {targetOutcome && (
            <div className="flex items-start gap-2">
              <TrendingUp className="h-4 w-4 mt-0.5 text-green-600" />
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Target Outcome</p>
                <p className="text-sm">{targetOutcome}</p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
