'use client';

import { UnifiedCycleView } from './UnifiedCycleView';
import { cn } from '@/lib/utils';

interface CampaignSequencesProps {
  clientId: string;
  cycleId?: string;  // Filter to specific cycle
  className?: string;
}

/**
 * CampaignSequences - Displays campaign cycles for a client
 *
 * Simplified to always show UnifiedCycleView (no more legacy toggle).
 * Pass cycleId to filter to a specific cycle, or omit to show current/latest.
 */
export function CampaignSequences({ clientId, cycleId, className }: CampaignSequencesProps) {
  return (
    <div className={cn('space-y-6', className)}>
      <UnifiedCycleView clientId={clientId} cycleId={cycleId} />
    </div>
  );
}
