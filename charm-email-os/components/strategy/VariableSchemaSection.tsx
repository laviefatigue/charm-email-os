'use client';

import { Badge } from '@/components/ui/badge';
import { Code, Sparkles, Database } from 'lucide-react';
import type { VariableSchema, VariableDefinition } from '@/lib/types';
import { cn } from '@/lib/utils';

interface VariableSchemaSectionProps {
  schema: VariableSchema;
  className?: string;
}

function VariableTag({ variable, showSource }: { variable: VariableDefinition; showSource?: boolean }) {
  return (
    <div className="inline-flex items-center gap-2 bg-purple-100 text-purple-800 rounded-md px-2.5 py-1.5 text-sm font-mono">
      <span>{`{{${variable.name}}}`}</span>
      {showSource && variable.source && (
        <span className="text-purple-600 text-xs">
          via {variable.source}
        </span>
      )}
    </div>
  );
}

function VariableGroup({
  title,
  icon: Icon,
  variables,
  showSource = false,
  color = 'purple',
}: {
  title: string;
  icon: React.ElementType;
  variables: VariableDefinition[];
  showSource?: boolean;
  color?: 'purple' | 'emerald' | 'blue';
}) {
  if (!variables || variables.length === 0) return null;

  const colorClasses = {
    purple: 'bg-purple-50 border-purple-200',
    emerald: 'bg-emerald-50 border-emerald-200',
    blue: 'bg-blue-50 border-blue-200',
  };

  const tagColors = {
    purple: 'bg-purple-100 text-purple-800',
    emerald: 'bg-emerald-100 text-emerald-800',
    blue: 'bg-blue-100 text-blue-800',
  };

  return (
    <div className={cn('rounded-lg border p-4', colorClasses[color])}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4" />
        <h5 className="text-sm font-semibold">{title}</h5>
        <Badge variant="secondary" className="text-xs">
          {variables.length}
        </Badge>
      </div>
      <div className="space-y-2">
        {variables.map((variable, idx) => (
          <div key={idx} className="flex items-start gap-3">
            <code className={cn('px-2 py-1 rounded text-sm font-mono whitespace-nowrap', tagColors[color])}>
              {`{{${variable.name}}}`}
            </code>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-muted-foreground">{variable.description}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {showSource && variable.source && (
                  <span className="text-xs text-muted-foreground/70">
                    Source: {variable.source}
                  </span>
                )}
                {variable.usedIn && variable.usedIn.length > 0 && (
                  <span className="text-xs text-muted-foreground/70 flex items-center gap-1">
                    Used in: {variable.usedIn.map((pos) => (
                      <Badge key={pos} variant="outline" className="text-[10px] px-1 py-0 h-4">
                        E{pos}
                      </Badge>
                    ))}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function VariableSchemaSection({ schema, className }: VariableSchemaSectionProps) {
  return (
    <div className={cn('space-y-4', className)}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <VariableGroup
          title="Core Variables"
          icon={Code}
          variables={schema.core}
          color="purple"
        />
        <VariableGroup
          title="High-Signal Variables"
          icon={Database}
          variables={schema.highSignal}
          showSource
          color="emerald"
        />
        <VariableGroup
          title="AI-Generated Variables"
          icon={Sparkles}
          variables={schema.aiGenerated}
          color="blue"
        />
      </div>
    </div>
  );
}
