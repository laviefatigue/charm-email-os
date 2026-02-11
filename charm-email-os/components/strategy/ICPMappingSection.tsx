'use client';

import { Users, Briefcase, Building2 } from 'lucide-react';
import type { ICPMapping, PainPoint, Objection } from '@/lib/types';
import { cn } from '@/lib/utils';
import { RequestRevisionButton } from './RequestRevisionButton';

interface ICPMappingSectionProps {
  icpMapping: ICPMapping;
  className?: string;
  onRequestRevisionTargetICP?: () => void;
  onRequestRevisionPainPoints?: (category?: string) => void;
  onRequestRevisionObjections?: (index?: number) => void;
  isSubmitting?: {
    targetICP?: boolean;
    painPoints?: boolean;
    objections?: boolean;
  };
}

function PainPointCard({
  painPoint,
  onRequestRevision,
  isSubmitting,
}: {
  painPoint: PainPoint;
  onRequestRevision?: () => void;
  isSubmitting?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4 group">
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {painPoint.category}
          </span>
          <h5 className="text-sm font-semibold mt-0.5">{painPoint.label}</h5>
        </div>
        {onRequestRevision && (
          <RequestRevisionButton
            onClick={onRequestRevision}
            isSubmitting={isSubmitting}
            iconOnly
            tooltip="Request revision"
            className="opacity-0 group-hover:opacity-100 transition-opacity"
            size="sm"
          />
        )}
      </div>
      <ul className="space-y-1.5">
        {painPoint.points.map((point, idx) => (
          <li key={idx} className="text-sm text-muted-foreground flex items-start gap-2">
            <span className="text-muted-foreground/40 select-none">•</span>
            <span>{point}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ObjectionCard({
  objection,
  onRequestRevision,
  isSubmitting,
}: {
  objection: Objection;
  onRequestRevision?: () => void;
  isSubmitting?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4 group">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{objection.objection}</p>
          <p className="text-sm text-muted-foreground mt-2">{objection.preemption}</p>
        </div>
        {onRequestRevision && (
          <RequestRevisionButton
            onClick={onRequestRevision}
            isSubmitting={isSubmitting}
            iconOnly
            tooltip="Request revision"
            className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            size="sm"
          />
        )}
      </div>
    </div>
  );
}

export function ICPMappingSection({
  icpMapping,
  className,
  onRequestRevisionTargetICP,
  onRequestRevisionPainPoints,
  onRequestRevisionObjections,
  isSubmitting,
}: ICPMappingSectionProps) {
  const { targetIcp, painPoints, objections } = icpMapping;

  return (
    <div className={cn('space-y-6', className)}>
      {/* Target ICP */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold">Target ICP</h4>
          {onRequestRevisionTargetICP && (
            <RequestRevisionButton
              onClick={onRequestRevisionTargetICP}
              isSubmitting={isSubmitting?.targetICP}
              tooltip="Request revision"
              iconOnly
            />
          )}
        </div>
        <div className="rounded-lg border bg-card p-4">
          <div className="grid grid-cols-3 gap-6">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Briefcase className="h-3.5 w-3.5" />
                Role
              </div>
              <p className="text-sm font-medium">{targetIcp.role}</p>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Building2 className="h-3.5 w-3.5" />
                Company Type
              </div>
              <p className="text-sm font-medium">{targetIcp.companyType}</p>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Users className="h-3.5 w-3.5" />
                Company Size
              </div>
              <p className="text-sm font-medium">{targetIcp.companySize}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Pain Points */}
      {painPoints && painPoints.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold">Pain Points</h4>
            {onRequestRevisionPainPoints && (
              <RequestRevisionButton
                onClick={() => onRequestRevisionPainPoints()}
                isSubmitting={isSubmitting?.painPoints}
                tooltip="Request revision for all"
                iconOnly
              />
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            {painPoints.map((painPoint, idx) => (
              <PainPointCard
                key={idx}
                painPoint={painPoint}
                onRequestRevision={onRequestRevisionPainPoints ? () => onRequestRevisionPainPoints(painPoint.category) : undefined}
                isSubmitting={isSubmitting?.painPoints}
              />
            ))}
          </div>
        </div>
      )}

      {/* Objections */}
      {objections && objections.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold">Objection Handling</h4>
            {onRequestRevisionObjections && (
              <RequestRevisionButton
                onClick={() => onRequestRevisionObjections()}
                isSubmitting={isSubmitting?.objections}
                tooltip="Request revision for all"
                iconOnly
              />
            )}
          </div>
          <div className="grid grid-cols-1 gap-3">
            {objections.map((objection, idx) => (
              <ObjectionCard
                key={idx}
                objection={objection}
                onRequestRevision={onRequestRevisionObjections ? () => onRequestRevisionObjections(idx) : undefined}
                isSubmitting={isSubmitting?.objections}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
