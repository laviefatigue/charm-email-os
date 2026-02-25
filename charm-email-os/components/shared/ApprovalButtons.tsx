'use client';

import { Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ApprovalButtonsProps {
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
  size?: 'sm' | 'default';
  className?: string;
}

export function ApprovalButtons({
  onApprove,
  onReject,
  disabled = false,
  size = 'sm',
  className,
}: ApprovalButtonsProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Button
        variant="outline"
        size={size === 'sm' ? 'icon' : 'default'}
        onClick={onApprove}
        disabled={disabled}
        className="text-green-600 hover:text-green-700 hover:bg-green-50 border-green-200 hover:border-green-300"
      >
        <Check className={cn(size === 'sm' ? 'h-4 w-4' : 'h-5 w-5')} />
        {size !== 'sm' && <span className="ml-2">Approve</span>}
      </Button>
      <Button
        variant="outline"
        size={size === 'sm' ? 'icon' : 'default'}
        onClick={onReject}
        disabled={disabled}
        className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200 hover:border-red-300"
      >
        <X className={cn(size === 'sm' ? 'h-4 w-4' : 'h-5 w-5')} />
        {size !== 'sm' && <span className="ml-2">Reject</span>}
      </Button>
    </div>
  );
}
