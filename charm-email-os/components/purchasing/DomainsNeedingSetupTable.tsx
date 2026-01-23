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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Loader2, Settings, Server, Clock, CheckCircle2, AlertCircle, RefreshCw, ShieldCheck, ShieldAlert, ShieldQuestion, Wrench } from 'lucide-react';
import type { Domain, NameserverStatus } from '@/lib/types';
import { isDnsReady, hoursUntilDnsReady } from '@/lib/types';
import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

interface DomainsNeedingSetupTableProps {
  domains: Domain[];
  onSetupClick: (selectedDomainIds: string[]) => void;
  isSettingUp?: boolean;
  onDomainsChange?: () => void;  // Callback to refresh domains after verification
}

export function DomainsNeedingSetupTable({
  domains,
  onSetupClick,
  isSettingUp = false,
  onDomainsChange,
}: DomainsNeedingSetupTableProps) {
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
  const [isVerifying, setIsVerifying] = useState(false);
  const [isFixingNs, setIsFixingNs] = useState(false);

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

  // Verify nameservers for selected domains
  const handleVerifyNameservers = useCallback(async () => {
    if (selectedDomains.size === 0) {
      toast.error('No domains selected');
      return;
    }

    setIsVerifying(true);
    try {
      const domainNames = purchasedDomains
        .filter(d => selectedDomains.has(d.id))
        .map(d => d.domainName || d.domain);

      const response = await fetch(`${API_BASE}/api/domain-sourcing/verify-nameservers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_names: domainNames }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Verification failed');
      }

      const data = await response.json();

      if (data.verified_count > 0) {
        toast.success(`Verified ${data.verified_count} domain(s)`);
      }
      if (data.mismatch_count > 0) {
        toast.warning(`${data.mismatch_count} domain(s) have incorrect nameservers`);
      }
      if (data.failed_count > 0) {
        toast.error(`${data.failed_count} domain(s) could not be verified`);
      }

      // Refresh domains list
      onDomainsChange?.();
    } catch (error: any) {
      toast.error(error.message || 'Failed to verify nameservers');
    } finally {
      setIsVerifying(false);
    }
  }, [selectedDomains, purchasedDomains, onDomainsChange]);

  // Fix nameservers for selected domains (set to DNSimple)
  const handleFixNameservers = useCallback(async () => {
    if (selectedDomains.size === 0) {
      toast.error('No domains selected');
      return;
    }

    // Get domains that need fixing (failed, mismatch, or pending)
    const domainsToFix = purchasedDomains
      .filter(d => selectedDomains.has(d.id))
      .filter(d => !d.nameserverStatus || d.nameserverStatus !== 'verified')
      .map(d => d.domainName || d.domain);

    if (domainsToFix.length === 0) {
      toast.info('All selected domains already have verified nameservers');
      return;
    }

    setIsFixingNs(true);
    try {
      const response = await fetch(`${API_BASE}/api/domain-sourcing/set-nameservers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_names: domainsToFix }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to set nameservers');
      }

      const data = await response.json();

      if (data.success_count > 0) {
        if (data.verified_count > 0) {
          toast.success(`Set nameservers for ${data.success_count} domain(s), ${data.verified_count} verified immediately`);
        } else {
          toast.success(`Set nameservers for ${data.success_count} domain(s). Verification pending.`);
        }
      }
      if (data.failed_count > 0) {
        toast.error(`Failed to set nameservers for ${data.failed_count} domain(s)`);
      }

      // Refresh domains list
      onDomainsChange?.();
    } catch (error: any) {
      toast.error(error.message || 'Failed to set nameservers');
    } finally {
      setIsFixingNs(false);
    }
  }, [selectedDomains, purchasedDomains, onDomainsChange]);

  // Count domains needing NS fix (selected domains that aren't verified)
  const domainsNeedingFix = useMemo(() => {
    return purchasedDomains
      .filter(d => selectedDomains.has(d.id))
      .filter(d => !d.nameserverStatus || d.nameserverStatus !== 'verified')
      .length;
  }, [purchasedDomains, selectedDomains]);

  // Get NS verification status badge
  const getNsStatusBadge = (domain: Domain) => {
    const status = domain.nameserverStatus || 'pending';

    switch (status) {
      case 'verified':
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-green-600 border-green-600">
                <ShieldCheck className="h-3 w-3 mr-1" />
                Verified
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Nameservers confirmed at {domain.selectedProvider || 'registrar'}.
              {domain.currentNameservers && (
                <>
                  <br />
                  Current: {domain.currentNameservers.slice(0, 2).join(', ')}...
                </>
              )}
            </TooltipContent>
          </Tooltip>
        );
      case 'mismatch':
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-amber-600 border-amber-600">
                <ShieldAlert className="h-3 w-3 mr-1" />
                Mismatch
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Nameservers don't match DNSimple requirements.
              {domain.currentNameservers && (
                <>
                  <br />
                  Found: {domain.currentNameservers.slice(0, 2).join(', ')}...
                </>
              )}
            </TooltipContent>
          </Tooltip>
        );
      case 'failed':
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-red-600 border-red-600">
                <AlertCircle className="h-3 w-3 mr-1" />
                Failed
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Could not verify nameservers at registrar.
              Domain may not be in Porkbun/Dynadot account.
            </TooltipContent>
          </Tooltip>
        );
      default:
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-gray-500 border-gray-300">
                <ShieldQuestion className="h-3 w-3 mr-1" />
                Pending
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Not yet verified. Click "Verify NS" to check.
            </TooltipContent>
          </Tooltip>
        );
    }
  };

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
              {selectedDomains.size} of {purchasedDomains.length} domains selected
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={selectedDomains.size === 0 || isVerifying}
              onClick={handleVerifyNameservers}
            >
              {isVerifying ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-1" />
              )}
              Verify NS
            </Button>
            {domainsNeedingFix > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={isFixingNs}
                onClick={handleFixNameservers}
                className="border-amber-500 text-amber-600 hover:bg-amber-50"
              >
                {isFixingNs ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Wrench className="h-4 w-4 mr-1" />
                )}
                Fix NS ({domainsNeedingFix})
              </Button>
            )}
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
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]"></TableHead>
            <TableHead className="w-[180px]">Domain</TableHead>
            <TableHead className="w-[60px] text-center">TLD</TableHead>
            <TableHead className="w-[110px] text-center">Status</TableHead>
            <TableHead className="w-[100px] text-center">NS Verified</TableHead>
            <TableHead className="w-[100px] text-center">DNS Ready</TableHead>
            <TableHead className="w-[90px] text-center">Provider</TableHead>
            <TableHead className="w-[120px]">Purchased</TableHead>
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
            const dnsReady = isDnsReady(domain);
            const hoursRemaining = hoursUntilDnsReady(domain);

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
                <TableCell className="w-[110px] text-center">
                  {getStatusBadge(domain.status)}
                </TableCell>
                <TableCell className="w-[100px] text-center">
                  {getNsStatusBadge(domain)}
                </TableCell>
                <TableCell className="w-[100px] text-center">
                  {domain.nameserversUpdatedAt ? (
                    dnsReady ? (
                      <Tooltip>
                        <TooltipTrigger>
                          <Badge variant="outline" className="text-green-600 border-green-600">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Ready
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          DNS propagated. Ready for Hypertide setup.
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <Tooltip>
                        <TooltipTrigger>
                          <Badge variant="outline" className="text-amber-600 border-amber-600">
                            <Clock className="h-3 w-3 mr-1" />
                            {hoursRemaining}h left
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          DNS propagating. ~{hoursRemaining} hours until ready.
                          <br />
                          Started: {new Date(domain.nameserversUpdatedAt).toLocaleString()}
                        </TooltipContent>
                      </Tooltip>
                    )
                  ) : (
                    <Tooltip>
                      <TooltipTrigger>
                        <Badge variant="outline" className="text-red-600 border-red-600">
                          <AlertCircle className="h-3 w-3 mr-1" />
                          No NS
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        Nameservers not set. This domain needs DNS configuration.
                      </TooltipContent>
                    </Tooltip>
                  )}
                </TableCell>
                <TableCell className="w-[90px] text-center">
                  <Badge variant="outline" className="text-xs capitalize">
                    <Server className="h-3 w-3 mr-1" />
                    {domain.selectedProvider || '?'}
                  </Badge>
                </TableCell>
                <TableCell className="w-[120px] text-muted-foreground text-sm">
                  {domain.purchasedAt
                    ? new Date(domain.purchasedAt).toLocaleDateString()
                    : domain.createdAt
                    ? new Date(domain.createdAt).toLocaleDateString()
                    : '-'}
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
