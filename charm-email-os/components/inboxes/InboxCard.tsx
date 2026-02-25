'use client';

import { Mail, Send, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, ApprovalButtons } from '@/components/shared';
import { WarmupProgress } from './WarmupProgress';
import type { Inbox } from '@/lib/types';
import { useInfrastructureStore } from '@/lib/stores';
import { cn } from '@/lib/utils';

interface InboxCardProps {
  inbox: Inbox;
  onEdit?: (inbox: Inbox) => void;
}

export function InboxCard({ inbox, onEdit }: InboxCardProps) {
  const { approveInbox, rejectInbox } = useInfrastructureStore();

  const handleApprove = () => {
    approveInbox(inbox.id);
    toast.success(`Inbox ${inbox.email} approved`);
  };

  const handleReject = () => {
    rejectInbox(inbox.id);
    toast.info(`Inbox ${inbox.email} rejected - click Edit to modify`);
  };

  const handleEdit = () => {
    onEdit?.(inbox);
  };

  const isPending = inbox.status === 'pending_approval';
  const isWarming = inbox.status === 'warming';
  const isActive = inbox.status === 'active';
  const isRejected = inbox.status === 'rejected';

  return (
    <Card className={cn(
      'transition-all hover:shadow-sm',
      isRejected && 'border-destructive/50 bg-destructive/5'
    )}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className={cn(
            'flex h-10 w-10 items-center justify-center rounded-lg',
            isRejected ? 'bg-destructive/10' : 'bg-muted'
          )}>
            <Mail className={cn(
              'h-5 w-5',
              isRejected ? 'text-destructive' : 'text-muted-foreground'
            )} />
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-medium truncate">{inbox.email}</p>
            <p className="text-sm text-muted-foreground">
              {inbox.firstName} {inbox.lastName}
            </p>

            <div className="flex items-center gap-2 mt-2">
              <StatusBadge status={inbox.status} />
              {isActive && inbox.dailySendLimit && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Send className="h-3 w-3" />
                  {inbox.dailySendLimit}/day
                </span>
              )}
            </div>

            {isWarming && inbox.warmupProgress !== undefined && (
              <WarmupProgress progress={inbox.warmupProgress} className="mt-3" />
            )}

            {isPending && (
              <div className="mt-3">
                <ApprovalButtons onApprove={handleApprove} onReject={handleReject} />
              </div>
            )}

            {isRejected && (
              <div className="mt-3">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={handleEdit}
                >
                  <Pencil className="h-4 w-4 mr-2" />
                  Edit & Resubmit
                </Button>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
