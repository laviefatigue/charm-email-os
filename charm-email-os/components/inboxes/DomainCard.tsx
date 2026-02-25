'use client';

import { Globe, Activity, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, ApprovalButtons } from '@/components/shared';
import type { Domain } from '@/lib/types';
import { useInfrastructureStore } from '@/lib/stores';
import { cn } from '@/lib/utils';

interface DomainCardProps {
  domain: Domain;
  isSelected?: boolean;
  onSelect?: () => void;
  onEdit?: (domain: Domain) => void;
}

export function DomainCard({ domain, isSelected, onSelect, onEdit }: DomainCardProps) {
  const { approveDomain, rejectDomain } = useInfrastructureStore();

  const handleApprove = () => {
    approveDomain(domain.id);
    toast.success(`Domain ${domain.domain} approved`);
  };

  const handleReject = () => {
    rejectDomain(domain.id);
    toast.info(`Domain ${domain.domain} rejected - click Edit to modify`);
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit?.(domain);
  };

  const isPending = domain.status === 'pending_approval';
  const isRejected = domain.status === 'rejected';

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:shadow-sm',
        isSelected && 'ring-2 ring-primary',
        isRejected && 'border-destructive/50 bg-destructive/5'
      )}
      onClick={onSelect}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              isRejected ? 'bg-destructive/10' : 'bg-muted'
            )}>
              <Globe className={cn(
                'h-5 w-5',
                isRejected ? 'text-destructive' : 'text-muted-foreground'
              )} />
            </div>
            <div className="min-w-0">
              <p className="font-medium truncate">{domain.domain}</p>
              <StatusBadge status={domain.status} className="mt-1" />
            </div>
          </div>

          {domain.healthScore !== undefined && domain.status === 'active' && (
            <div className="flex items-center gap-1 text-sm">
              <Activity className="h-4 w-4 text-green-500" />
              <span className="font-medium">{domain.healthScore}</span>
            </div>
          )}
        </div>

        {isPending && (
          <div className="mt-3 pt-3 border-t" onClick={(e) => e.stopPropagation()}>
            <ApprovalButtons onApprove={handleApprove} onReject={handleReject} />
          </div>
        )}

        {isRejected && (
          <div className="mt-3 pt-3 border-t" onClick={(e) => e.stopPropagation()}>
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
      </CardContent>
    </Card>
  );
}
