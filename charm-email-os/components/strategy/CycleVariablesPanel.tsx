'use client';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CycleVariable, VariableLevel } from '@/lib/types';

// Core variables that are always available in every email
const CORE_VARIABLES: CycleVariable[] = [
  { name: '{{first_name}}', description: "Prospect's first name" },
  { name: '{{company_name}}', description: "Prospect's company" },
  { name: '{{role_title}}', description: "Prospect's job title" },
];

interface CycleVariablesPanelProps {
  cycleVariables: CycleVariable[];
  campaignVariables: CycleVariable[];
  copyVariables: CycleVariable[];
  className?: string;
}

const LEVEL_STYLES: Record<VariableLevel, { bg: string; text: string; label: string }> = {
  cycle: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'Cycle' },
  campaign: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Campaign' },
  copy: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'Core' },
};

interface VariableTagProps {
  variable: CycleVariable;
  level: VariableLevel;
}

function VariableTag({ variable, level }: VariableTagProps) {
  const style = LEVEL_STYLES[level];

  return (
    <div className="group relative">
      <Badge
        variant="secondary"
        className={cn(
          'font-mono text-xs cursor-help',
          style.bg,
          style.text,
          'hover:ring-2 hover:ring-offset-1 hover:ring-purple-400'
        )}
      >
        {variable.name}
      </Badge>
      {/* Tooltip on hover */}
      <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block z-50">
        <div className="bg-popover text-popover-foreground p-3 rounded-lg shadow-lg border text-sm min-w-[200px] max-w-[300px]">
          <p className="font-medium mb-1">{variable.name}</p>
          <p className="text-muted-foreground text-xs">{variable.description}</p>
          {variable.source && (
            <p className="text-xs mt-1">
              <span className="text-muted-foreground">Source:</span> {variable.source}
            </p>
          )}
          {variable.leadGenUse && (
            <p className="text-xs mt-1">
              <span className="text-muted-foreground">Lead Gen:</span> {variable.leadGenUse}
            </p>
          )}
          {variable.value && (
            <p className="text-xs mt-1 font-mono bg-muted px-1 py-0.5 rounded">
              = {variable.value}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function VariableSection({
  title,
  variables,
  level,
  emptyMessage,
}: {
  title: string;
  variables: CycleVariable[];
  level: VariableLevel;
  emptyMessage: string;
}) {
  const style = LEVEL_STYLES[level];
  // Deduplicate variables by name
  const uniqueVars = variables.filter(
    (v, i, arr) => arr.findIndex(x => x.name === v.name) === i
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-medium">{title}</h4>
        <Badge variant="outline" className={cn('text-xs', style.bg, style.text)}>
          {style.label}
        </Badge>
        <span className="text-xs text-muted-foreground">({uniqueVars.length})</span>
      </div>
      {uniqueVars.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {uniqueVars.map((variable, idx) => (
            <VariableTag key={`${variable.name}-${idx}`} variable={variable} level={level} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">{emptyMessage}</p>
      )}
    </div>
  );
}

export function CycleVariablesPanel({
  cycleVariables,
  campaignVariables,
  copyVariables,
  className,
}: CycleVariablesPanelProps) {
  // Merge core variables with any additional copy variables
  const coreVariables = [
    ...CORE_VARIABLES,
    ...copyVariables.filter(v =>
      !CORE_VARIABLES.some(c => c.name === v.name)
    ),
  ];

  return (
    <div className={cn('space-y-4', className)}>
      {/* Breadcrumb explanation */}
      <div className="text-xs text-muted-foreground flex items-center gap-2 border-b pb-2">
        <span>Variable Inheritance:</span>
        <span className="flex items-center gap-1">
          <Badge variant="outline" className={cn('text-[10px]', LEVEL_STYLES.cycle.bg, LEVEL_STYLES.cycle.text)}>
            Cycle
          </Badge>
          <span>→</span>
          <Badge variant="outline" className={cn('text-[10px]', LEVEL_STYLES.campaign.bg, LEVEL_STYLES.campaign.text)}>
            Campaign
          </Badge>
          <span>→</span>
          <Badge variant="outline" className={cn('text-[10px]', LEVEL_STYLES.copy.bg, LEVEL_STYLES.copy.text)}>
            Core
          </Badge>
        </span>
      </div>

      <VariableSection
        title="Cycle Variables"
        variables={cycleVariables}
        level="cycle"
        emptyMessage="No cycle-level variables defined"
      />

      <VariableSection
        title="Campaign Variables"
        variables={campaignVariables}
        level="campaign"
        emptyMessage="No campaign-specific variables"
      />

      <VariableSection
        title="Core Variables"
        variables={coreVariables}
        level="copy"
        emptyMessage="No core variables"
      />
    </div>
  );
}
