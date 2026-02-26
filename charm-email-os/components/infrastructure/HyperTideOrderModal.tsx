'use client';

/**
 * HyperTide Order Modal
 * Auto-selects domains using FIFO (oldest purchased + DNS ready first)
 */

import { useState, useEffect } from 'react';
import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Waves,
  Check,
  Loader2,
  AlertTriangle,
  Server,
  Mail,
  DollarSign,
  Package,
} from 'lucide-react';
import { PROVIDER_CONFIG, TLD_DISPLAY } from '@/lib/types/infrastructure';
import type { ProviderType, HyperTideOrderPreview } from '@/lib/types/infrastructure';

interface HyperTideOrderModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider: ProviderType;
  onConfirm: (request: { domainIds: string[]; provider: ProviderType; orderCount: number }) => Promise<void>;
}

export function HyperTideOrderModal({
  open,
  onOpenChange,
  provider,
  onConfirm,
}: HyperTideOrderModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orderCount, setOrderCount] = useState(1);

  const {
    getHyperTideOrderPreview,
    getDomainsReadyForHyperTide,
    selectDomainsForHyperTide,
    clearSelection,
  } = useWaterfallStore();

  const config = PROVIDER_CONFIG[provider];
  const isEntra = provider === 'entra';

  // Get ready domains for this provider
  const readyDomains = getDomainsReadyForHyperTide(provider);
  const maxOrders = Math.floor(readyDomains.length / config.domainsPerOrder);

  // Auto-select domains when modal opens or order count changes
  useEffect(() => {
    if (open && orderCount > 0) {
      // Select the right number of domains for the order count
      const domainsNeeded = orderCount * config.domainsPerOrder;
      const domainsToSelect = readyDomains.slice(0, domainsNeeded);
      // This will update the selection in the store
    }
  }, [open, orderCount]);

  const preview = getHyperTideOrderPreview(provider);

  const handleConfirm = async () => {
    if (!preview || preview.selectedDomains.length === 0) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await onConfirm({
        domainIds: preview.selectedDomains.map((d) => d.domainId),
        provider,
        orderCount: preview.orderCount,
      });
      clearSelection();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create HyperTide order');
    } finally {
      setIsSubmitting(false);
    }
  };

  // No domains ready
  if (readyDomains.length === 0) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Waves className="w-5 h-5 text-indigo-600" />
              Create {isEntra ? 'Entra' : 'Google'} Order
            </DialogTitle>
            <DialogDescription>
              No domains are ready for {isEntra ? 'Entra' : 'Google'} provisioning.
            </DialogDescription>
          </DialogHeader>
          <div className="py-6 text-center">
            <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto mb-3" />
            <p className="text-sm text-slate-600">
              Domains must be purchased and have DNS verified before creating a HyperTide order.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Not enough for a single order
  if (maxOrders === 0) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Waves className="w-5 h-5 text-indigo-600" />
              Create {isEntra ? 'Entra' : 'Google'} Order
            </DialogTitle>
          </DialogHeader>
          <div className="py-6 text-center">
            <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto mb-3" />
            <p className="text-sm text-slate-600 mb-2">
              Need {config.domainsPerOrder} domains for one {isEntra ? 'Entra' : 'Google'} order.
            </p>
            <p className="text-sm text-slate-500">
              You have {readyDomains.length} domain{readyDomains.length !== 1 ? 's' : ''} ready.
              Need {config.domainsPerOrder - readyDomains.length} more.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Calculate preview for current order count
  const domainsForOrder = readyDomains.slice(0, orderCount * config.domainsPerOrder);
  const totalInboxes = orderCount * config.inboxesPerOrder;
  const monthlyCost = orderCount * config.costPerOrder;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Waves className="w-5 h-5 text-indigo-600" />
            Create {isEntra ? 'Entra' : 'Google'} Order
          </DialogTitle>
          <DialogDescription>
            Auto-selected domains using FIFO (oldest purchased + DNS ready first)
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Order Count Selector */}
          <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
            <div className="flex-1">
              <Label htmlFor="order-count" className="text-sm font-medium">
                Number of Orders
              </Label>
              <p className="text-xs text-slate-500 mt-0.5">
                Each order: {config.domainsPerOrder} domains × {config.inboxesPerDomain} inboxes ={' '}
                {config.inboxesPerOrder} inboxes
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOrderCount(Math.max(1, orderCount - 1))}
                disabled={orderCount <= 1}
              >
                -
              </Button>
              <Input
                id="order-count"
                type="number"
                min={1}
                max={maxOrders}
                value={orderCount}
                onChange={(e) =>
                  setOrderCount(Math.min(maxOrders, Math.max(1, parseInt(e.target.value) || 1)))
                }
                className="w-16 text-center"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOrderCount(Math.min(maxOrders, orderCount + 1))}
                disabled={orderCount >= maxOrders}
              >
                +
              </Button>
            </div>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-white border rounded-lg p-3 text-center">
              <Server className={`w-5 h-5 mx-auto mb-1 ${isEntra ? 'text-blue-500' : 'text-red-500'}`} />
              <div className="text-lg font-bold text-slate-900">{domainsForOrder.length}</div>
              <div className="text-xs text-slate-500">Domains</div>
            </div>
            <div className="bg-white border rounded-lg p-3 text-center">
              <Mail className="w-5 h-5 mx-auto mb-1 text-indigo-500" />
              <div className="text-lg font-bold text-slate-900">{totalInboxes}</div>
              <div className="text-xs text-slate-500">Inboxes</div>
            </div>
            <div className="bg-white border rounded-lg p-3 text-center">
              <Package className="w-5 h-5 mx-auto mb-1 text-emerald-500" />
              <div className="text-lg font-bold text-slate-900">{orderCount}</div>
              <div className="text-xs text-slate-500">Orders</div>
            </div>
            <div className="bg-white border rounded-lg p-3 text-center">
              <DollarSign className="w-5 h-5 mx-auto mb-1 text-amber-500" />
              <div className="text-lg font-bold text-slate-900">${monthlyCost}</div>
              <div className="text-xs text-slate-500">/month</div>
            </div>
          </div>

          {/* Selected Domains */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-slate-700">
                Selected Domains (FIFO Order)
              </div>
              <Badge variant="outline" className={isEntra ? 'bg-blue-50 text-blue-700' : 'bg-red-50 text-red-700'}>
                {isEntra ? 'Entra' : 'Google'} • {config.inboxesPerDomain} inboxes/domain
              </Badge>
            </div>
            <ScrollArea className="h-[180px] border rounded-lg">
              <div className="p-3 space-y-1">
                {domainsForOrder.map((domain, idx) => {
                  const orderNum = Math.floor(idx / config.domainsPerOrder) + 1;
                  const tld = domain.domainName.split('.').pop() as keyof typeof TLD_DISPLAY;
                  const purchaseDate = domain.purchasedAt
                    ? new Date(domain.purchasedAt).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })
                    : '';

                  return (
                    <div
                      key={domain.domainId}
                      className={`flex items-center justify-between py-1.5 px-2 rounded ${
                        idx % config.domainsPerOrder === 0 && idx > 0
                          ? 'border-t-2 border-slate-200 mt-2 pt-3'
                          : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="text-xs bg-slate-100 text-slate-600 w-8 justify-center"
                        >
                          #{orderNum}
                        </Badge>
                        <span className="font-medium text-sm text-slate-900">
                          {domain.domainName}
                        </span>
                        <Badge
                          variant="outline"
                          className={`text-xs ${TLD_DISPLAY[tld]?.color ?? ''}`}
                        >
                          .{tld}
                        </Badge>
                      </div>
                      <div className="text-xs text-slate-400">Purchased {purchaseDate}</div>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </div>

          {/* Capacity Check */}
          {preview && !preview.withinLimit && (
            <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 rounded-lg p-3">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Package Limit Warning</p>
                <p className="text-xs mt-0.5">
                  This order exceeds your current package allocation. Contact your account manager
                  to increase your package limit.
                </p>
              </div>
            </div>
          )}

          {/* Info */}
          <div className="flex items-start gap-2 text-xs text-slate-500 bg-blue-50 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-blue-700">What happens next:</p>
              <ul className="mt-1 space-y-0.5 text-blue-600">
                <li>• Order will be submitted to HyperTide for processing</li>
                <li>• Inboxes will be created and configured automatically</li>
                <li>• Inboxes will sync to EmailBison within 24-48 hours</li>
                <li>• Warmup will begin automatically once synced</li>
              </ul>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg p-3">
              <AlertTriangle className="w-4 h-4" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isSubmitting || domainsForOrder.length === 0}
            className={isEntra ? 'bg-blue-600 hover:bg-blue-700' : 'bg-red-600 hover:bg-red-700'}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Creating Order...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Create {orderCount} Order{orderCount !== 1 ? 's' : ''} (${monthlyCost}/mo)
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
