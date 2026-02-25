'use client';

import { cn, formatStatus } from '@/lib/utils';
import { STATUS_COLORS } from '@/lib/types';

interface StatusBadgeProps {
  status: string;
  className?: string;
  variant?: 'default' | 'outline';
}

export function StatusBadge({ status, className, variant = 'default' }: StatusBadgeProps) {
  const colors = STATUS_COLORS[status] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        variant === 'default' && colors.bg,
        variant === 'default' && colors.text,
        variant === 'outline' && 'border bg-transparent',
        variant === 'outline' && colors.text,
        className
      )}
    >
      {formatStatus(status)}
    </span>
  );
}
