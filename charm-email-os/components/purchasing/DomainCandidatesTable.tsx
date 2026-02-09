'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Check, X, DollarSign, ShoppingCart, RefreshCw, ArrowUpDown } from 'lucide-react';
import { domainSourcingApi } from '@/lib/api';
import { toast } from 'sonner';
import type { Domain } from '@/lib/types';

type SortOption = 'status' | 'price' | 'name';

const PRICE_THRESHOLD = 15.0;

interface DomainCandidatesTableProps {
  domains: Domain[];
  clientId: string;
  onDomainUpdate?: () => void;
}

type ActionState = {
  loading: boolean;
  error: string | null;
};

export function DomainCandidatesTable({
  domains,
  clientId,
  onDomainUpdate,
}: DomainCandidatesTableProps) {
  // Track action states per domain
  const [actionStates, setActionStates] = useState<Record<string, ActionState>>({});
  // Track prices after check (dual provider)
  const [prices, setPrices] = useState<Record<string, {
    price: string;
    available: boolean;
    porkbun?: { price: string | null; available: boolean };
    dynadot?: { price: string | null; available: boolean };
    bestProvider?: string;
  }>>({});
  // Track selected domains for bulk purchase
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
  // Track bulk purchase loading
  const [isBulkPurchasing, setIsBulkPurchasing] = useState(false);
  // Track bulk price check loading
  const [isBulkCheckingPrices, setIsBulkCheckingPrices] = useState(false);
  // Sort option
  const [sortBy, setSortBy] = useState<SortOption>('status');

  const setDomainState = useCallback((domainId: string, state: ActionState) => {
    setActionStates((prev) => ({ ...prev, [domainId]: state }));
  }, []);

  // Hydrate prices from cached database values on mount
  // This ensures sorting works correctly with existing price data
  useEffect(() => {
    const initialPrices: Record<string, {
      price: string;
      available: boolean;
      porkbun?: { price: string | null; available: boolean };
      dynadot?: { price: string | null; available: boolean };
      bestProvider?: string;
    }> = {};

    domains.forEach((d) => {
      // Skip if we already have a price for this domain (from manual check)
      if (prices[d.id]) return;

      // Check if domain has cached price data from DB
      const hasPriceData = d.cachedPrice || d.porkbunPrice || d.dynadotPrice;
      if (hasPriceData) {
        initialPrices[d.id] = {
          price: d.cachedPrice ? String(d.cachedPrice) : '',
          available: d.porkbunAvailable || d.dynadotAvailable || false,
          porkbun: {
            available: d.porkbunAvailable ?? false,
            price: d.porkbunPrice ? String(d.porkbunPrice) : null,
          },
          dynadot: {
            available: d.dynadotAvailable ?? false,
            price: d.dynadotPrice ? String(d.dynadotPrice) : null,
          },
          bestProvider: d.selectedProvider || undefined,
        };
      }
    });

    if (Object.keys(initialPrices).length > 0) {
      setPrices((prev) => ({ ...initialPrices, ...prev }));
    }
  }, [domains]);

  // Filter out purchased domains (they belong in DomainsNeedingSetupTable)
  // Only show: pending, approved, rejected/denied
  const filteredDomains = useMemo(() => {
    return domains.filter(d =>
      d.status === 'pending' ||
      d.status === 'pending_approval' ||
      d.status === 'approved' ||
      d.status === 'rejected' ||
      d.status === 'denied'
    );
  }, [domains]);

  // Sort domains based on selected sort option
  const sortedDomains = useMemo(() => {
    const statusOrder: Record<string, number> = {
      pending: 0,
      pending_approval: 0,
      approved: 1,
      rejected: 2,
      denied: 2,
    };

    return [...filteredDomains].sort((a, b) => {
      // Denied/rejected domains always at bottom regardless of sort
      const aIsDenied = a.status === 'rejected' || a.status === 'denied';
      const bIsDenied = b.status === 'rejected' || b.status === 'denied';
      if (aIsDenied && !bIsDenied) return 1;
      if (bIsDenied && !aIsDenied) return -1;

      if (sortBy === 'status') {
        const aOrder = statusOrder[a.status] ?? 3;
        const bOrder = statusOrder[b.status] ?? 3;
        if (aOrder !== bOrder) return aOrder - bOrder;
        // Same status — secondary sort by name
        return (a.domainName || a.domain || '').localeCompare(b.domainName || b.domain || '');
      }

      if (sortBy === 'price') {
        const priceInfoA = prices[a.id];
        const priceInfoB = prices[b.id];
        const priceA = priceInfoA?.price ? parseFloat(priceInfoA.price) :
                       (a.cachedPrice ? parseFloat(String(a.cachedPrice)) : Infinity);
        const priceB = priceInfoB?.price ? parseFloat(priceInfoB.price) :
                       (b.cachedPrice ? parseFloat(String(b.cachedPrice)) : Infinity);
        if (priceA !== priceB) return priceA - priceB;
        return (a.domainName || a.domain || '').localeCompare(b.domainName || b.domain || '');
      }

      // sortBy === 'name'
      return (a.domainName || a.domain || '').localeCompare(b.domainName || b.domain || '');
    });
  }, [filteredDomains, prices, sortBy]);

  // Count domains that need price check (use filtered domains)
  const domainsNeedingPriceCheck = useMemo(() => {
    return filteredDomains.filter(d => d.status === 'approved' && !prices[d.id]).length;
  }, [filteredDomains, prices]);

  // Get domains that qualify for purchase (approved, available, under threshold)
  const qualifiedDomains = useMemo(() => {
    return filteredDomains.filter((d) => {
      if (d.status !== 'approved') return false;
      const priceInfo = prices[d.id];
      if (!priceInfo || !priceInfo.available) return false;
      const priceNum = parseFloat(priceInfo.price);
      return !isNaN(priceNum) && priceNum <= PRICE_THRESHOLD;
    });
  }, [filteredDomains, prices]);

  // Get selected domains that are actually qualified
  const selectedQualified = useMemo(() => {
    return qualifiedDomains.filter((d) => selectedDomains.has(d.id));
  }, [qualifiedDomains, selectedDomains]);

  const handleSelectAll = useCallback(() => {
    if (selectedQualified.length === qualifiedDomains.length) {
      // Deselect all
      setSelectedDomains(new Set());
    } else {
      // Select all qualified
      setSelectedDomains(new Set(qualifiedDomains.map((d) => d.id)));
    }
  }, [qualifiedDomains, selectedQualified.length]);

  const handleToggleSelect = useCallback((domainId: string) => {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return next;
    });
  }, []);

  const handleApprove = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      await domainSourcingApi.approveDomain(domainId);
      onDomainUpdate?.();
    } catch (err) {
      setDomainState(domainId, { loading: false, error: 'Failed to approve' });
    }
  }, [onDomainUpdate, setDomainState]);

  const handleDeny = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      await domainSourcingApi.denyDomain(domainId);
      onDomainUpdate?.();
    } catch (err) {
      setDomainState(domainId, { loading: false, error: 'Failed to deny' });
    }
  }, [onDomainUpdate, setDomainState]);

  const handleUnapprove = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      await domainSourcingApi.unapproveDomain(domainId);
      // Clear cached price when unapproving
      setPrices((prev) => {
        const next = { ...prev };
        delete next[domainId];
        return next;
      });
      // Remove from selection if selected
      setSelectedDomains((prev) => {
        const next = new Set(prev);
        next.delete(domainId);
        return next;
      });
      onDomainUpdate?.();
    } catch (err) {
      setDomainState(domainId, { loading: false, error: 'Failed to unapprove' });
    }
  }, [onDomainUpdate, setDomainState]);

  const handleCheckPrice = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      const result = await domainSourcingApi.checkPrice(domainId);
      setPrices((prev) => ({
        ...prev,
        [domainId]: {
          price: result.price || 'N/A',
          available: result.available,
          porkbun: result.porkbun ? {
            price: result.porkbun.price,
            available: result.porkbun.available,
          } : undefined,
          dynadot: result.dynadot ? {
            price: result.dynadot.price,
            available: result.dynadot.available,
          } : undefined,
          bestProvider: result.bestProvider || undefined,
        },
      }));
      setDomainState(domainId, { loading: false, error: null });
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to check price';
      setDomainState(domainId, { loading: false, error: errorMsg });
    }
  }, [setDomainState]);

  // Bulk check all approved domains
  const handleCheckAllPrices = useCallback(async () => {
    // Get all approved domains that need price check (use filteredDomains)
    const approvedDomains = filteredDomains.filter(d => d.status === 'approved' && !prices[d.id]);
    if (approvedDomains.length === 0) {
      toast.info('All approved domains already have prices checked');
      return;
    }

    setIsBulkCheckingPrices(true);

    try {
      const result = await domainSourcingApi.checkPricesBulk({ clientId });

      // Update prices state with results
      const newPrices: typeof prices = {};
      for (const item of result.results) {
        if (!item.error) {
          newPrices[item.domainId] = {
            price: item.bestPrice || 'N/A',
            available: (item.porkbunAvailable || item.dynadotAvailable) ?? false,
            porkbun: item.porkbunPrice !== undefined ? {
              price: item.porkbunPrice ?? null,
              available: item.porkbunAvailable ?? false,
            } : undefined,
            dynadot: item.dynadotPrice !== undefined ? {
              price: item.dynadotPrice ?? null,
              available: item.dynadotAvailable ?? false,
            } : undefined,
            bestProvider: item.bestProvider,
          };
        }
      }
      setPrices(prev => ({ ...prev, ...newPrices }));

      toast.success(
        `Checked ${result.checkedCount} domains. ${result.availableCount} available.${result.errorCount > 0 ? ` ${result.errorCount} errors.` : ''}`
      );
      onDomainUpdate?.();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Bulk price check failed';
      toast.error(errorMsg);
    } finally {
      setIsBulkCheckingPrices(false);
    }
  }, [filteredDomains, prices, clientId, onDomainUpdate]);

  const handlePurchase = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      const result = await domainSourcingApi.purchaseSingle(domainId);
      if (result.success) {
        onDomainUpdate?.();
      } else {
        setDomainState(domainId, { loading: false, error: result.error || 'Purchase failed' });
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Purchase failed';
      setDomainState(domainId, { loading: false, error: errorMsg });
    }
  }, [onDomainUpdate, setDomainState]);

  const handleBulkPurchase = useCallback(async () => {
    if (selectedQualified.length === 0) return;

    setIsBulkPurchasing(true);
    let successCount = 0;
    const errors: string[] = [];

    for (const domain of selectedQualified) {
      const domainName = domain.domainName || domain.domain || domain.id;
      try {
        const result = await domainSourcingApi.purchaseSingle(domain.id);
        if (result.success) {
          successCount++;
        } else {
          errors.push(result.error || `${domainName}: Purchase failed`);
        }
      } catch (err: unknown) {
        // Extract detailed error message from API response
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        errors.push(`${domainName}: ${errorMsg}`);
      }
    }

    setIsBulkPurchasing(false);
    setSelectedDomains(new Set());

    if (successCount > 0) {
      toast.success(`Purchased ${successCount} domain${successCount > 1 ? 's' : ''}`);
    }
    if (errors.length > 0) {
      // Show detailed error message
      toast.error(errors[0], { duration: 8000 });
    }

    onDomainUpdate?.();
  }, [selectedQualified, onDomainUpdate]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
      case 'pending_approval':
        return <Badge variant="outline" className="text-yellow-600 border-yellow-600">Pending</Badge>;
      case 'approved':
        return <Badge variant="outline" className="text-blue-600 border-blue-600">Approved</Badge>;
      case 'rejected':
        return <Badge variant="outline" className="text-red-600 border-red-600">Rejected</Badge>;
      case 'purchased':
        return <Badge variant="outline" className="text-green-600 border-green-600">Purchased</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const renderPriceCell = (domain: Domain) => {
    const priceInfo = prices[domain.id];
    const state = actionStates[domain.id];

    if (state?.loading) {
      return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
    }

    if (priceInfo) {
      if (!priceInfo.available) {
        return <span className="text-red-500 text-sm">Unavailable</span>;
      }

      // Render dual pricing
      const porkbunPrice = priceInfo.porkbun?.price ? parseFloat(priceInfo.porkbun.price) : null;
      const dynadotPrice = priceInfo.dynadot?.price ? parseFloat(priceInfo.dynadot.price) : null;
      const isBestPorkbun = priceInfo.bestProvider === 'porkbun';
      const isBestDynadot = priceInfo.bestProvider === 'dynadot';

      return (
        <div className="flex flex-col gap-0.5 text-xs">
          {priceInfo.porkbun && (
            <div className={`flex items-center gap-1 ${isBestPorkbun ? 'font-semibold' : 'text-muted-foreground'}`}>
              <span className="w-12">PB:</span>
              {priceInfo.porkbun.available && porkbunPrice ? (
                <span className={porkbunPrice <= PRICE_THRESHOLD ? 'text-green-600' : 'text-orange-500'}>
                  ${priceInfo.porkbun.price}
                  {isBestPorkbun && <span className="ml-1 text-green-600">✓</span>}
                </span>
              ) : (
                <span className="text-red-400">N/A</span>
              )}
            </div>
          )}
          {priceInfo.dynadot && (
            <div className={`flex items-center gap-1 ${isBestDynadot ? 'font-semibold' : 'text-muted-foreground'}`}>
              <span className="w-12">DD:</span>
              {priceInfo.dynadot.available && dynadotPrice ? (
                <span className={dynadotPrice <= PRICE_THRESHOLD ? 'text-green-600' : 'text-orange-500'}>
                  ${priceInfo.dynadot.price}
                  {isBestDynadot && <span className="ml-1 text-green-600">✓</span>}
                </span>
              ) : (
                <span className="text-red-400">N/A</span>
              )}
            </div>
          )}
          {!priceInfo.porkbun && !priceInfo.dynadot && (
            <span className={`font-medium ${parseFloat(priceInfo.price) <= PRICE_THRESHOLD ? 'text-green-600' : 'text-orange-500'}`}>
              ${priceInfo.price}
            </span>
          )}
        </div>
      );
    }

    // Show check price button for approved domains
    if (domain.status === 'approved') {
      return (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => handleCheckPrice(domain.id)}
        >
          <DollarSign className="h-3 w-3 mr-1" />
          Check
        </Button>
      );
    }

    return <span className="text-muted-foreground">-</span>;
  };

  const renderActions = (domain: Domain) => {
    const state = actionStates[domain.id] || { loading: false, error: null };
    const priceInfo = prices[domain.id];
    const status = domain.status;

    if (state.loading) {
      return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
    }

    if (state.error) {
      return (
        <div className="flex items-center gap-2">
          <span className="text-xs text-red-500">{state.error}</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setDomainState(domain.id, { loading: false, error: null })}
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      );
    }

    // Pending: Show Approve/Deny (centered)
    if (status === 'pending' || status === 'pending_approval') {
      return (
        <div className="flex gap-2 justify-center">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-green-600 hover:text-green-700 hover:bg-green-50"
            onClick={() => handleApprove(domain.id)}
          >
            <Check className="h-3 w-3 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-red-600 hover:text-red-700 hover:bg-red-50"
            onClick={() => handleDeny(domain.id)}
          >
            <X className="h-3 w-3 mr-1" />
            Deny
          </Button>
        </div>
      );
    }

    // Approved: Show Unapprove button to revert to pending
    if (status === 'approved') {
      return (
        <div className="flex justify-center">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-orange-600 hover:text-orange-700 hover:bg-orange-50"
            onClick={() => handleUnapprove(domain.id)}
          >
            <X className="h-3 w-3 mr-1" />
            Unapprove
          </Button>
        </div>
      );
    }

    // Rejected: Just show dash (centered)
    if (status === 'rejected') {
      return <span className="text-sm text-muted-foreground block text-center">-</span>;
    }

    // Purchased: Show completed (centered)
    if (status === 'purchased') {
      return <span className="text-sm text-green-600 block text-center">Owned</span>;
    }

    return null;
  };

  const isQualified = (domain: Domain) => {
    if (domain.status !== 'approved') return false;
    const priceInfo = prices[domain.id];
    if (!priceInfo || !priceInfo.available) return false;
    const priceNum = parseFloat(priceInfo.price);
    return !isNaN(priceNum) && priceNum <= PRICE_THRESHOLD;
  };

  if (sortedDomains.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No domain candidates. Generate some to get started.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Sort & Count Bar */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          {sortedDomains.length} domain{sortedDomains.length !== 1 ? 's' : ''}
        </span>
        <div className="flex items-center gap-2">
          <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
          <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
            <SelectTrigger className="h-8 w-35 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="status">Sort by Status</SelectItem>
              <SelectItem value="price">Sort by Price</SelectItem>
              <SelectItem value="name">Sort by Name</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Refresh Prices Bar */}
      {domainsNeedingPriceCheck > 0 && (
        <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
          <span className="text-sm text-blue-700">
            {domainsNeedingPriceCheck} approved domains available for purchase
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={isBulkCheckingPrices}
            className="border-blue-300 text-blue-700 hover:bg-blue-100"
            onClick={handleCheckAllPrices}
          >
            {isBulkCheckingPrices ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            Refresh Prices
          </Button>
        </div>
      )}

      {/* Bulk Purchase Bar */}
      {qualifiedDomains.length > 0 && (
        <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
          <div className="flex items-center gap-3">
            <Checkbox
              checked={selectedQualified.length === qualifiedDomains.length && qualifiedDomains.length > 0}
              onCheckedChange={handleSelectAll}
            />
            <span className="text-sm text-green-700">
              {selectedQualified.length} of {qualifiedDomains.length} qualified domains selected
              <span className="text-xs text-green-600 ml-2">(under ${PRICE_THRESHOLD})</span>
            </span>
          </div>
          <Button
            size="sm"
            disabled={selectedQualified.length === 0 || isBulkPurchasing}
            className="bg-green-600 hover:bg-green-700"
            onClick={handleBulkPurchase}
          >
            {isBulkPurchasing ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <ShoppingCart className="h-4 w-4 mr-1" />
            )}
            Purchase Selected ({selectedQualified.length})
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]"></TableHead>
            <TableHead className="w-[200px]">Domain</TableHead>
            <TableHead className="w-[60px] text-center">TLD</TableHead>
            <TableHead className="w-[90px] text-center">Status</TableHead>
            <TableHead className="w-[150px]">Price</TableHead>
            <TableHead className="w-[180px] text-center">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedDomains.map((domain) => {
            const domainName = domain.domainName || domain.domain || '';
            const parts = domainName.split('.');
            const tld = parts.length > 1 ? `.${parts[parts.length - 1]}` : '';
            const qualified = isQualified(domain);

            return (
              <TableRow key={domain.id} className={qualified && selectedDomains.has(domain.id) ? 'bg-green-50/50' : ''}>
                <TableCell className="w-[40px]">
                  {qualified && (
                    <Checkbox
                      checked={selectedDomains.has(domain.id)}
                      onCheckedChange={() => handleToggleSelect(domain.id)}
                    />
                  )}
                </TableCell>
                <TableCell className="w-[200px] font-medium">{domainName}</TableCell>
                <TableCell className="w-[60px] text-center">
                  <Badge variant="secondary">{tld}</Badge>
                </TableCell>
                <TableCell className="w-[90px] text-center">{getStatusBadge(domain.status)}</TableCell>
                <TableCell className="w-[150px]">{renderPriceCell(domain)}</TableCell>
                <TableCell className="w-[180px] text-center">{renderActions(domain)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
