'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Settings, Server } from 'lucide-react';
import type { Domain } from '@/lib/types';

interface DomainsNeedingSetupTableProps {
  domains: Domain[];
  onSetupClick: (selectedDomainIds: string[]) => void;
  isSettingUp?: boolean;
}

export function DomainsNeedingSetupTable({
  domains,
  onSetupClick,
  isSettingUp = false,
}: DomainsNeedingSetupTableProps) {
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());

  // Filter only purchased domains (not provisioning)
  const purchasedDomains = useMemo(() =>
    domains.filter(d => d.status === 'purchased'),
    [domains]
  );

  // Provisioning domains (being set up)
  const provisioningDomains = useMemo(() =>
    domains.filter(d => d.status === 'provisioning'),
    [domains]
  );

  const handleSelectAll = useCallback(() => {
    if (selectedDomains.size === purchasedDomains.length) {
      setSelectedDomains(new Set());
    } else {
      setSelectedDomains(new Set(purchasedDomains.map(d => d.id)));
    }
  }, [purchasedDomains, selectedDomains.size]);

  const handleToggleSelect = useCallback((domainId: string) => {
    setSelectedDomains(prev => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return next;
    });
  }, []);

  const handleSetupClick = useCallback(() => {
    onSetupClick(Array.from(selectedDomains));
  }, [selectedDomains, onSetupClick]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'purchased':
        return <Badge variant="outline" className="text-orange-600 border-orange-600">Needs Setup</Badge>;
      case 'provisioning':
        return (
          <Badge variant="outline" className="text-blue-600 border-blue-600">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            Provisioning
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  if (domains.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No domains need inbox setup.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Setup Action Bar */}
      {purchasedDomains.length > 0 && (
        <div className="flex items-center justify-between p-3 bg-orange-50 rounded-lg border border-orange-200">
          <div className="flex items-center gap-3">
            <Checkbox
              checked={selectedDomains.size === purchasedDomains.length && purchasedDomains.length > 0}
              onCheckedChange={handleSelectAll}
            />
            <span className="text-sm text-orange-700">
              {selectedDomains.size} of {purchasedDomains.length} domains selected for inbox setup
            </span>
          </div>
          <Button
            size="sm"
            disabled={selectedDomains.size === 0 || isSettingUp}
            className="bg-orange-600 hover:bg-orange-700"
            onClick={handleSetupClick}
          >
            {isSettingUp ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <Settings className="h-4 w-4 mr-1" />
            )}
            Setup Inboxes ({selectedDomains.size})
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]"></TableHead>
            <TableHead className="w-[200px]">Domain</TableHead>
            <TableHead className="w-[60px] text-center">TLD</TableHead>
            <TableHead className="w-[120px] text-center">Status</TableHead>
            <TableHead className="w-[100px] text-center">Provider</TableHead>
            <TableHead className="w-[150px]">Purchased</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {domains.map((domain) => {
            const domainName = domain.domainName || domain.domain || '';
            const parts = domainName.split('.');
            const tld = parts.length > 1 ? `.${parts[parts.length - 1]}` : '';
            const isPurchased = domain.status === 'purchased';
            const isProvisioning = domain.status === 'provisioning';
            const isSelected = selectedDomains.has(domain.id);

            return (
              <TableRow
                key={domain.id}
                className={isSelected ? 'bg-orange-50/50' : isProvisioning ? 'bg-blue-50/30' : ''}
              >
                <TableCell className="w-[40px]">
                  {isPurchased && (
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => handleToggleSelect(domain.id)}
                      disabled={isSettingUp}
                    />
                  )}
                  {isProvisioning && (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                  )}
                </TableCell>
                <TableCell className="w-[200px] font-medium">{domainName}</TableCell>
                <TableCell className="w-[60px] text-center">
                  <Badge variant="secondary">{tld}</Badge>
                </TableCell>
                <TableCell className="w-[120px] text-center">
                  {getStatusBadge(domain.status)}
                </TableCell>
                <TableCell className="w-[100px] text-center">
                  <Badge variant="outline" className="text-xs">
                    <Server className="h-3 w-3 mr-1" />
                    {/* Provider info could come from domain metadata */}
                    Auto
                  </Badge>
                </TableCell>
                <TableCell className="w-[150px] text-muted-foreground text-sm">
                  {domain.createdAt ? new Date(domain.createdAt).toLocaleDateString() : '-'}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {/* Summary */}
      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{purchasedDomains.length} awaiting setup</span>
        {provisioningDomains.length > 0 && (
          <span className="text-blue-600">{provisioningDomains.length} provisioning</span>
        )}
      </div>
    </div>
  );
}
