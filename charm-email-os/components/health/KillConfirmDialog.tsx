'use client';

import { Skull, AlertTriangle, Mail, Globe } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import type { KillTrigger } from '@/lib/types/health';
import { KILL_TRIGGER_THRESHOLDS } from '@/lib/types/health';

interface KillConfirmDialogProps {
  trigger: KillTrigger | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isExecuting?: boolean;
}

export function KillConfirmDialog({
  trigger,
  open,
  onOpenChange,
  onConfirm,
  isExecuting = false,
}: KillConfirmDialogProps) {
  if (!trigger) return null;

  const threshold = KILL_TRIGGER_THRESHOLDS[trigger.type];
  const isInstant = trigger.severity === 'instant';

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-red-700">
            <Skull className="h-5 w-5" />
            Confirm Kill Inbox
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-4 pt-2">
              {/* Inbox info */}
              <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="h-4 w-4 text-gray-500" />
                  <span className="font-medium text-gray-900">{trigger.inboxEmail}</span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Globe className="h-4 w-4 text-gray-500" />
                  <span className="text-gray-600">{trigger.domainName}</span>
                </div>
              </div>

              {/* Trigger reason */}
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5" />
                <div className="text-sm">
                  <span className="font-medium">{threshold.label}:</span>{' '}
                  <span className="text-gray-600">
                    {trigger.value.toFixed(trigger.value < 1 ? 2 : 0)} (threshold: {trigger.threshold})
                  </span>
                </div>
              </div>

              {/* Severity badge */}
              <div className="flex items-center gap-2">
                <Badge
                  variant={isInstant ? 'destructive' : 'secondary'}
                  className={!isInstant ? 'bg-yellow-100 text-yellow-800' : ''}
                >
                  {isInstant ? 'Instant Kill' : 'Confirming'}
                </Badge>
              </div>

              {/* Warning */}
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-sm text-red-800">
                  <strong>This action is permanent.</strong> The inbox will be marked as dead and
                  removed from all active campaigns. It cannot be undone.
                </p>
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isExecuting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isExecuting}
            className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
          >
            <Skull className="h-4 w-4 mr-2" />
            {isExecuting ? 'Killing...' : 'Kill Inbox'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
