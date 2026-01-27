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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Loader2, Settings, Server, Clock, CheckCircle2, AlertCircle, RefreshCw, ShieldCheck, ShieldAlert, ShieldQuestion, Wrench, Calendar, AlertTriangle, Cloud, Mail } from 'lucide-react';
import type { Domain, NameserverStatus } from '@/lib/types';
import { isDnsReady, hoursUntilDnsReady, isDomainAgeEligible } from '@/lib/types';
import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

interface DomainsNeedingSetupTableProps {
  domains: Domain[];
  onSetupClick: (selectedDomainIds: string[], hasAgeOverride: boolean) => void;
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

  // Admin override confirmation dialog state
  const [overrideDialogOpen, setOverrideDialogOpen] = useState(false);
  const [pendingOverrideDomain, setPendingOverrideDomain] = useState<Domain | null>(null);
  // Track domains that have been force-selected (admin override)
  const [forceSelectedDomains, setForceSelectedDomains] = useState<Set<string>>(new Set());

  // Filter only purchased domains (not provisioning)
  const purchasedDomains = useMemo(() =>
    domains.filter(d => d.status === 'purchased'),
    [domains]
  );

  // Domains eligible for setup (30+ days old OR exempt, AND has verified NS)
  const eligibleDomains = useMemo(() =>
    purchasedDomains.filter(d => d.isSetupEligible === true),
    [purchasedDomains]
  );

  // Domains too young for setup (< 30 days and not exempt)
  const tooYoungDomains = useMemo(() =>
    purchasedDomains.filter(d => !isDomainAgeEligible(d)),
    [purchasedDomains]
  );

  // Provisioning domains (being set up)
  const provisioningDomains = useMemo(() =>
    domains.filter(d => d.status === 'provisioning'),
    [domains]
  );

  const handleSelectAll = useCallback(() => {
    // Only select eligible domains
    if (selectedDomains.size === eligibleDomains.length && eligibleDomains.length > 0) {
      setSelectedDomains(new Set());
    } else {
      setSelectedDomains(new Set(eligibleDomains.map(d => d.id)));
    }
  }, [eligibleDomains, selectedDomains.size]);

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

  // Handle clicking on a young domain checkbox - show override confirmation
  const handleYoungDomainClick = useCallback((domain: Domain) => {
    setPendingOverrideDomain(domain);
    setOverrideDialogOpen(true);
  }, []);

  // Confirm the admin override - add domain to force-selected and selected sets
  const handleConfirmOverride = useCallback(() => {
    if (pendingOverrideDomain) {
      setForceSelectedDomains(prev => new Set(prev).add(pendingOverrideDomain.id));
      setSelectedDomains(prev => new Set(prev).add(pendingOverrideDomain.id));
      toast.warning(`Admin override: ${pendingOverrideDomain.domainName || pendingOverrideDomain.domain} selected despite being ${pendingOverrideDomain.domainAgeDays ?? 0} days old`);
    }
    setOverrideDialogOpen(false);
    setPendingOverrideDomain(null);
  }, [pendingOverrideDomain]);

  // Cancel the override
  const handleCancelOverride = useCallback(() => {
    setOverrideDialogOpen(false);
    setPendingOverrideDomain(null);
  }, []);

  const handleSetupClick = useCallback(() => {
    // Check if any selected domain was force-selected (admin override)
    const hasAgeOverride = Array.from(selectedDomains).some(id => forceSelectedDomains.has(id));
    onSetupClick(Array.from(selectedDomains), hasAgeOverride);
  }, [selectedDomains, forceSelectedDomains, onSetupClick]);

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
      if (data.propagating_count > 0) {
        toast.info(`${data.propagating_count} domain(s) propagating (set recently, wait up to 48h)`);
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

    // Get domains that need fixing (failed, mismatch, or pending - NOT propagating)
    const domainsToFix = purchasedDomains
      .filter(d => selectedDomains.has(d.id))
      .filter(d => {
        const status = d.nameserverStatus;
        // Only fix if failed, mismatch, or never set (pending)
        // Propagating domains don't need fixing - they're already set correctly
        return !status || status === 'pending' || status === 'failed' || status === 'mismatch';
      })
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

  // Count domains needing NS fix (selected domains that aren't verified or propagating)
  // Propagating domains don't need fixing - they just need to wait for DNS propagation
  const domainsNeedingFix = useMemo(() => {
    return purchasedDomains
      .filter(d => selectedDomains.has(d.id))
      .filter(d => {
        const status = d.nameserverStatus;
        // Only needs fix if failed, mismatch, or never set (pending)
        return !status || status === 'pending' || status === 'failed' || status === 'mismatch';
      })
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
      case 'propagating':
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-blue-600 border-blue-600">
                <Clock className="h-3 w-3 mr-1" />
                Propagating
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Nameservers set to DNSimple, waiting for DNS propagation.
              <br />
              This can take up to 48 hours.
              {domain.nameserversUpdatedAt && (
                <>
                  <br />
                  Set: {new Date(domain.nameserversUpdatedAt).toLocaleString()}
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

  // Get domain age badge
  const getAgeBadge = (domain: Domain) => {
    // Exempt domains (legacy/active) bypass age check
    if (domain.isAgeExempt) {
      return (
        <Tooltip>
          <TooltipTrigger>
            <Badge variant="outline" className="text-blue-600 border-blue-600">
              <ShieldCheck className="h-3 w-3 mr-1" />
              Exempt
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            Legacy/active domain - age check bypassed
          </TooltipContent>
        </Tooltip>
      );
    }

    // Has registration date - show age
    if (domain.registrationDate || domain.domainAgeDays !== undefined) {
      const ageDays = domain.domainAgeDays ?? 0;
      const daysLeft = domain.daysUntilAvailable ?? (30 - ageDays);

      if (ageDays >= 30 || daysLeft <= 0) {
        // Domain is old enough
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-green-600 border-green-600">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                {ageDays}d
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Domain is {ageDays} days old - eligible for setup
            </TooltipContent>
          </Tooltip>
        );
      } else {
        // Domain is too young
        return (
          <Tooltip>
            <TooltipTrigger>
              <Badge variant="outline" className="text-amber-600 border-amber-600">
                <Clock className="h-3 w-3 mr-1" />
                {daysLeft}d left
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Domain is only {ageDays} days old.
              <br />
              Available for setup in {daysLeft} days.
              {domain.registrationDate && (
                <>
                  <br />
                  Registered: {new Date(domain.registrationDate).toLocaleDateString()}
                </>
              )}
            </TooltipContent>
          </Tooltip>
        );
      }
    }

    // No registration date available
    return (
      <Badge variant="outline" className="text-gray-500 border-gray-300">
        <Calendar className="h-3 w-3 mr-1" />
        Unknown
      </Badge>
    );
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
              checked={selectedDomains.size === eligibleDomains.length && eligibleDomains.length > 0}
              onCheckedChange={handleSelectAll}
              disabled={eligibleDomains.length === 0}
            />
            <span className="text-sm text-orange-700">
              {selectedDomains.size} of {eligibleDomains.length} eligible domains selected
              {tooYoungDomains.length > 0 && (
                <span className="text-amber-600 ml-2">
                  ({tooYoungDomains.length} too young)
                </span>
              )}
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
            <TableHead className="w-20 text-center">Age</TableHead>
            <TableHead className="w-[90px] text-center">Infra Type</TableHead>
            <TableHead className="w-[90px] text-center">Registrar</TableHead>
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
                    domain.isSetupEligible || forceSelectedDomains.has(domain.id) ? (
                      // Eligible domain OR force-selected (admin override)
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => handleToggleSelect(domain.id)}
                        disabled={isSettingUp}
                        className={forceSelectedDomains.has(domain.id) ? 'border-amber-500' : ''}
                      />
                    ) : !isDomainAgeEligible(domain) ? (
                      // Young domain - show clickable checkbox with warning style
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            onClick={() => handleYoungDomainClick(domain)}
                            disabled={isSettingUp}
                            className="inline-flex items-center justify-center"
                          >
                            <Checkbox
                              checked={false}
                              className="border-amber-400 opacity-70 hover:opacity-100 cursor-pointer pointer-events-none"
                              disabled
                            />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <div className="flex items-center gap-1">
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                            Domain is only {domain.domainAgeDays ?? 0} days old.
                          </div>
                          Click to override (admin only).
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      // NS not verified - truly disabled
                      <Tooltip>
                        <TooltipTrigger>
                          <Checkbox disabled checked={false} className="opacity-50" />
                        </TooltipTrigger>
                        <TooltipContent>
                          Nameservers must be verified before setup.
                        </TooltipContent>
                      </Tooltip>
                    )
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
                <TableCell className="w-20 text-center">
                  {getAgeBadge(domain)}
                </TableCell>
                <TableCell className="w-[90px] text-center">
                  {domain.infrastructureType ? (
                    <Tooltip>
                      <TooltipTrigger>
                        <Badge
                          variant="outline"
                          className={
                            domain.infrastructureType === 'entra'
                              ? 'text-blue-600 border-blue-600'
                              : 'text-red-600 border-red-600'
                          }
                        >
                          {domain.infrastructureType === 'entra' ? (
                            <Cloud className="h-3 w-3 mr-1" />
                          ) : (
                            <Mail className="h-3 w-3 mr-1" />
                          )}
                          {domain.infrastructureType === 'entra' ? 'Entra' : 'Google'}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        {domain.infrastructureType === 'entra'
                          ? 'Microsoft Entra (50 inboxes/domain)'
                          : 'Google Workspace (3 inboxes/domain)'}
                        {domain.infrastructureSetAt && (
                          <>
                            <br />
                            Set: {new Date(domain.infrastructureSetAt).toLocaleDateString()}
                          </>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <Badge variant="outline" className="text-gray-400 border-gray-300">
                      —
                    </Badge>
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
        {eligibleDomains.length > 0 && (
          <span className="text-green-600">{eligibleDomains.length} eligible</span>
        )}
        {tooYoungDomains.length > 0 && (
          <span className="text-amber-600">{tooYoungDomains.length} too young (&lt;30 days)</span>
        )}
        {forceSelectedDomains.size > 0 && (
          <span className="text-amber-500">{forceSelectedDomains.size} override</span>
        )}
        {provisioningDomains.length > 0 && (
          <span className="text-blue-600">{provisioningDomains.length} provisioning</span>
        )}
      </div>

      {/* Admin Override Confirmation Dialog */}
      <Dialog open={overrideDialogOpen} onOpenChange={setOverrideDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Domain Age Warning
            </DialogTitle>
            <DialogDescription asChild>
              <div className="space-y-3 pt-2">
                <p>
                  <strong>{pendingOverrideDomain?.domainName || pendingOverrideDomain?.domain}</strong> is only{' '}
                  <strong className="text-amber-600">{pendingOverrideDomain?.domainAgeDays ?? 0} days old</strong>.
                </p>
                <p>
                  Setting up inboxes on domains younger than 30 days may negatively affect email deliverability.
                  ESPs often flag new domains as potential spam sources.
                </p>
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-amber-800 text-sm">
                  <strong>Recommendation:</strong> Wait until{' '}
                  {pendingOverrideDomain?.availableForSetupAt
                    ? new Date(pendingOverrideDomain.availableForSetupAt).toLocaleDateString()
                    : `${pendingOverrideDomain?.daysUntilAvailable ?? 30} more days`}{' '}
                  for optimal deliverability.
                </div>
              </div>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={handleCancelOverride}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmOverride}
              className="bg-amber-600 hover:bg-amber-700"
            >
              <AlertTriangle className="h-4 w-4 mr-1" />
              Proceed Anyway
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
