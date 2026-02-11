'use client';

import React from 'react';
import { Button, type ButtonProps } from '@/components/ui/button';
import { RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface RequestRevisionButtonProps extends Omit<ButtonProps, 'onClick'> {
  onClick: (e?: React.MouseEvent<HTMLButtonElement>) => void;
  isSubmitting?: boolean;
  label?: string;
  tooltip?: string;
  iconOnly?: boolean;
}

export function RequestRevisionButton({
  onClick,
  isSubmitting = false,
  label = 'Request Revision',
  tooltip,
  iconOnly = false,
  variant = 'outline',
  size = 'sm',
  className,
  ...props
}: RequestRevisionButtonProps) {
  const button = (
    <Button
      variant={variant}
      size={iconOnly ? 'icon' : size}
      onClick={onClick}
      disabled={isSubmitting}
      className={cn(
        // Square corners to highlight action, border styling
        'rounded-sm border-primary/50 text-muted-foreground hover:text-foreground hover:bg-primary/5 hover:border-primary',
        iconOnly && 'h-8 w-8',
        className
      )}
      {...props}
    >
      {isSubmitting ? (
        <>
          <Loader2 className={cn('h-4 w-4 animate-spin', !iconOnly && 'mr-1.5')} />
          {!iconOnly && <span>Submitting...</span>}
        </>
      ) : (
        <>
          <RefreshCw className={cn('h-4 w-4', !iconOnly && 'mr-1.5')} />
          {!iconOnly && <span>{label}</span>}
        </>
      )}
    </Button>
  );

  if (tooltip || iconOnly) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>
            <p>{tooltip || label}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return button;
}

// Keep backward compatibility alias
export { RequestRevisionButton as RegenerateButton };
