'use client';

import { Badge } from '@/components/ui/badge';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VariableLevel } from '@/lib/types';

interface VariablesBreadcrumbProps {
  currentLevel: VariableLevel;
  showAllLevels?: boolean;
  className?: string;
}

const LEVELS: { level: VariableLevel; label: string; description: string }[] = [
  { level: 'cycle', label: 'Cycle', description: 'Applies to all 4 campaigns' },
  { level: 'campaign', label: 'Campaign', description: 'Applies to all 4 emails' },
  { level: 'copy', label: 'Copy', description: 'Used in email content' },
];

const LEVEL_STYLES: Record<VariableLevel, { bg: string; text: string; activeBg: string; activeText: string }> = {
  cycle: { bg: 'bg-purple-100/50', text: 'text-purple-600', activeBg: 'bg-purple-500', activeText: 'text-white' },
  campaign: { bg: 'bg-blue-100/50', text: 'text-blue-600', activeBg: 'bg-blue-500', activeText: 'text-white' },
  copy: { bg: 'bg-green-100/50', text: 'text-green-600', activeBg: 'bg-green-500', activeText: 'text-white' },
};

export function VariablesBreadcrumb({
  currentLevel,
  showAllLevels = true,
  className,
}: VariablesBreadcrumbProps) {
  const currentIndex = LEVELS.findIndex((l) => l.level === currentLevel);

  if (!showAllLevels) {
    const style = LEVEL_STYLES[currentLevel];
    const levelInfo = LEVELS.find((l) => l.level === currentLevel);
    return (
      <Badge className={cn(style.activeBg, style.activeText, className)}>
        {levelInfo?.label} Variable
      </Badge>
    );
  }

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {LEVELS.map((levelInfo, index) => {
        const style = LEVEL_STYLES[levelInfo.level];
        const isActive = levelInfo.level === currentLevel;
        const isPast = index < currentIndex;

        return (
          <div key={levelInfo.level} className="flex items-center">
            {index > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground mx-1" />}
            <Badge
              variant="secondary"
              className={cn(
                'text-xs transition-colors',
                isActive
                  ? cn(style.activeBg, style.activeText)
                  : isPast
                  ? cn(style.bg, style.text, 'opacity-70')
                  : 'bg-muted text-muted-foreground opacity-50'
              )}
              title={levelInfo.description}
            >
              {levelInfo.label}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}

// Compact version for inline use
export function VariableLevelBadge({
  level,
  className,
}: {
  level: VariableLevel;
  className?: string;
}) {
  const style = LEVEL_STYLES[level];
  const levelInfo = LEVELS.find((l) => l.level === level);

  return (
    <Badge
      variant="secondary"
      className={cn('text-[10px]', style.bg, style.text, className)}
      title={levelInfo?.description}
    >
      {levelInfo?.label}
    </Badge>
  );
}
