'use client';

import { Users, Briefcase, Building2 } from 'lucide-react';
import type { ICPMapping, PainPoint, Objection } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ICPMappingSectionProps {
  icpMapping: ICPMapping;
  className?: string;
}

function PainPointCard({ painPoint }: { painPoint: PainPoint }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {painPoint.category}
        </span>
        <h5 className="text-sm font-semibold mt-0.5">{painPoint.label}</h5>
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

function ObjectionCard({ objection }: { objection: Objection }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">{objection.objection}</p>
      <p className="text-sm text-muted-foreground mt-2">{objection.preemption}</p>
    </div>
  );
}

export function ICPMappingSection({
  icpMapping,
  className,
}: ICPMappingSectionProps) {
  const { targetIcp, painPoints, objections } = icpMapping;

  return (
    <div className={cn('space-y-6', className)}>
      {/* Target ICP */}
      <div>
        <h4 className="text-sm font-semibold mb-3">Target ICP</h4>
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
          <h4 className="text-sm font-semibold mb-3">Pain Points</h4>
          <div className="grid grid-cols-2 gap-4">
            {painPoints.map((painPoint, idx) => (
              <PainPointCard key={idx} painPoint={painPoint} />
            ))}
          </div>
        </div>
      )}

      {/* Objections */}
      {objections && objections.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Objection Handling</h4>
          <div className="grid grid-cols-1 gap-3">
            {objections.map((objection, idx) => (
              <ObjectionCard key={idx} objection={objection} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
