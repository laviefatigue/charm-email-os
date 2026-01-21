'use client';

import { useState, useCallback } from 'react';
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
import { Loader2, Check, X, DollarSign, ShoppingCart, RefreshCw } from 'lucide-react';
import { domainSourcingApi } from '@/lib/api';
import type { Domain } from '@/lib/types';

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
  // Track prices after check
  const [prices, setPrices] = useState<Record<string, { price: string; available: boolean }>>({});

  const setDomainState = useCallback((domainId: string, state: ActionState) => {
    setActionStates((prev) => ({ ...prev, [domainId]: state }));
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

  const handleCheckPrice = useCallback(async (domainId: string) => {
    setDomainState(domainId, { loading: true, error: null });
    try {
      const result = await domainSourcingApi.checkPrice(domainId);
      setPrices((prev) => ({
        ...prev,
        [domainId]: {
          price: result.price || 'N/A',
          available: result.available,
        },
      }));
      setDomainState(domainId, { loading: false, error: null });
      onDomainUpdate?.();
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to check price';
      setDomainState(domainId, { loading: false, error: errorMsg });
    }
  }, [onDomainUpdate, setDomainState]);

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

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
      case 'pending_approval':
        return <Badge variant="outline" className="text-yellow-600 border-yellow-600">Pending</Badge>;
      case 'approved':
        return <Badge variant="outline" className="text-blue-600 border-blue-600">Approved</Badge>;
      case 'denied':
      case 'rejected':
        return <Badge variant="outline" className="text-red-600 border-red-600">Denied</Badge>;
      case 'purchased':
        return <Badge variant="outline" className="text-green-600 border-green-600">Purchased</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
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

    // Pending: Show Approve/Deny
    if (status === 'pending' || status === 'pending_approval') {
      return (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="text-green-600 hover:text-green-700 hover:bg-green-50"
            onClick={() => handleApprove(domain.id)}
          >
            <Check className="h-3 w-3 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
            onClick={() => handleDeny(domain.id)}
          >
            <X className="h-3 w-3 mr-1" />
            Deny
          </Button>
        </div>
      );
    }

    // Approved without price: Show Check Price
    if (status === 'approved' && !priceInfo) {
      return (
        <Button
          size="sm"
          variant="outline"
          onClick={() => handleCheckPrice(domain.id)}
        >
          <DollarSign className="h-3 w-3 mr-1" />
          Check Price
        </Button>
      );
    }

    // Approved with price: Show Purchase button
    if (status === 'approved' && priceInfo) {
      if (!priceInfo.available) {
        return <span className="text-sm text-red-500">Not Available</span>;
      }
      return (
        <Button
          size="sm"
          variant="default"
          className="bg-green-600 hover:bg-green-700"
          onClick={() => handlePurchase(domain.id)}
        >
          <ShoppingCart className="h-3 w-3 mr-1" />
          Purchase ${priceInfo.price}
        </Button>
      );
    }

    // Denied: Just show status
    if (status === 'denied' || status === 'rejected') {
      return <span className="text-sm text-muted-foreground">-</span>;
    }

    // Purchased: Show completed
    if (status === 'purchased') {
      return <span className="text-sm text-green-600">Completed</span>;
    }

    return null;
  };

  if (domains.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No domain candidates. Generate some to get started.
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Domain</TableHead>
          <TableHead>TLD</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Price</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {domains.map((domain) => {
          const priceInfo = prices[domain.id];
          const domainName = domain.domainName || domain.domain || '';
          const parts = domainName.split('.');
          const tld = parts.length > 1 ? `.${parts[parts.length - 1]}` : '';

          return (
            <TableRow key={domain.id}>
              <TableCell className="font-medium">{domainName}</TableCell>
              <TableCell>
                <Badge variant="secondary">{tld}</Badge>
              </TableCell>
              <TableCell>{getStatusBadge(domain.status)}</TableCell>
              <TableCell>
                {priceInfo ? (
                  priceInfo.available ? (
                    <span className="text-green-600 font-medium">${priceInfo.price}</span>
                  ) : (
                    <span className="text-red-500">Unavailable</span>
                  )
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell className="text-right">{renderActions(domain)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
