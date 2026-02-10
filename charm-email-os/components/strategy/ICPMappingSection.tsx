'use client';

import { Badge } from '@/components/ui/badge';
import { Users, Briefcase, Building2, AlertCircle, Shield } from 'lucide-react';
import type { ICPMapping, PainPoint, Objection } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ICPMappingSectionProps {
  icpMapping: ICPMapping;
  className?: string;
}

// Pain point category colors
const CATEGORY_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  'Tech Debt': { bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-500' },
  'Talent': { bg: 'bg-blue-50', border: 'border-blue-200', icon: 'text-blue-500' },
  'Competition': { bg: 'bg-purple-50', border: 'border-purple-200', icon: 'text-purple-500' },
  'Ops': { bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-500' },
  'default': { bg: 'bg-gray-50', border: 'border-gray-200', icon: 'text-gray-500' },
};

function PainPointCard({ painPoint }: { painPoint: PainPoint }) {
  const colors = CATEGORY_COLORS[painPoint.category] || CATEGORY_COLORS.default;

  return (
    <div className={cn('rounded-lg border p-4', colors.bg, colors.border)}>
      <div className="flex items-center gap-2 mb-2">
        <Badge variant="outline" className="text-xs font-medium">
          {painPoint.category}
        </Badge>
        <span className="text-sm font-medium text-foreground">{painPoint.label}</span>
      </div>
      <ul className="space-y-1.5">
        {painPoint.points.map((point, idx) => (
          <li key={idx} className="text-sm text-muted-foreground flex items-start gap-2">
            <span className="text-muted-foreground/50 mt-1">-</span>
            {point}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ObjectionRow({ objection }: { objection: Objection }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-3 pr-4">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
          <span className="text-sm">{objection.objection}</span>
        </div>
      </td>
      <td className="py-3">
        <div className="flex items-start gap-2">
          <Shield className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
          <span className="text-sm text-muted-foreground">{objection.preemption}</span>
        </div>
      </td>
    </tr>
  );
}

export function ICPMappingSection({ icpMapping, className }: ICPMappingSectionProps) {
  const { targetIcp, painPoints, objections } = icpMapping;

  return (
    <div className={cn('space-y-6', className)}>
      {/* Target ICP */}
      <div className="bg-primary/5 rounded-lg p-4 border border-primary/10">
        <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Users className="h-4 w-4" />
          Target ICP
        </h4>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Briefcase className="h-3 w-3" />
              Role
            </div>
            <p className="text-sm font-medium">{targetIcp.role}</p>
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Building2 className="h-3 w-3" />
              Company Type
            </div>
            <p className="text-sm font-medium">{targetIcp.companyType}</p>
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Users className="h-3 w-3" />
              Company Size
            </div>
            <p className="text-sm font-medium">{targetIcp.companySize}</p>
          </div>
        </div>
      </div>

      {/* Pain Points */}
      {painPoints && painPoints.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Pain Points by Category</h4>
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
          <h4 className="text-sm font-semibold mb-3">Objection Preemption</h4>
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left text-xs font-medium text-muted-foreground p-3 w-1/2">
                    Objection
                  </th>
                  <th className="text-left text-xs font-medium text-muted-foreground p-3 w-1/2">
                    Preemption Strategy
                  </th>
                </tr>
              </thead>
              <tbody>
                {objections.map((objection, idx) => (
                  <ObjectionRow key={idx} objection={objection} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
