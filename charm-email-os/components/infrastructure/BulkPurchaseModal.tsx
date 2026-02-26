'use client';

/**
 * Bulk Purchase Modal
 * Invoice-style display of selected domains with registrar breakdown
 */

import { useState } from 'react';
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
import {
  ShoppingCart,
  Check,
  Loader2,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import { TLD_DISPLAY } from '@/lib/types/infrastructure';
import type { BulkPurchasePreview } from '@/lib/types/infrastructure';

interface BulkPurchaseModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (domainIds: string[]) => Promise<void>;
}

export function BulkPurchaseModal({
  open,
  onOpenChange,
  onConfirm,
}: BulkPurchaseModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { getBulkPurchasePreview, clearSelection } = useWaterfallStore();
  const preview = getBulkPurchasePreview();

  const handleConfirm = async () => {
    if (!preview) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await onConfirm(preview.domains.map((d) => d.domainId));
      clearSelection();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to purchase domains');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!preview) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bulk Purchase</DialogTitle>
            <DialogDescription>
              No purchasable domains selected. Select domains that are under budget and not yet
              purchased.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingCart className="w-5 h-5 text-indigo-600" />
            Purchase {preview.totalDomains} Domain{preview.totalDomains !== 1 ? 's' : ''}
          </DialogTitle>
          <DialogDescription>
            Review the domains and registrar breakdown before confirming purchase
          </DialogDescription>
        </DialogHeader>

        {/* Domain List */}
        <div className="space-y-4">
          <div className="text-sm font-medium text-slate-700">Domains</div>
          <ScrollArea className="h-[200px] border rounded-lg">
            <div className="p-3 space-y-1">
              {preview.domains.map((domain, idx) => {
                const tld = domain.domainName.split('.').pop() as keyof typeof TLD_DISPLAY;
                return (
                  <div
                    key={domain.domainId}
                    className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-50"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400 w-6">{idx + 1}.</span>
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
                    <div className="flex items-center gap-3">
                      <Badge
                        variant="outline"
                        className={
                          domain.registrar === 'porkbun'
                            ? 'bg-pink-50 text-pink-700 border-pink-200'
                            : 'bg-orange-50 text-orange-700 border-orange-200'
                        }
                      >
                        {domain.registrar === 'porkbun' ? 'PB' : 'DD'}
                      </Badge>
                      <span className="text-sm font-medium text-slate-700 w-16 text-right">
                        ${domain.price.toFixed(2)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>

          <Separator />

          {/* Registrar Breakdown */}
          <div className="space-y-3">
            <div className="text-sm font-medium text-slate-700">Registrar Breakdown</div>
            <div className="bg-slate-50 rounded-lg p-4 space-y-2">
              {preview.breakdown.map((item) => (
                <div
                  key={item.registrar}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={
                        item.registrar === 'porkbun'
                          ? 'bg-pink-50 text-pink-700 border-pink-200'
                          : 'bg-orange-50 text-orange-700 border-orange-200'
                      }
                    >
                      {item.registrar === 'porkbun' ? 'Porkbun' : 'Dynadot'}
                    </Badge>
                    <span className="text-slate-600">
                      × {item.domainCount} domain{item.domainCount !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <span className="font-medium text-slate-900">
                    ${item.subtotal.toFixed(2)}
                  </span>
                </div>
              ))}

              <Separator className="my-2" />

              {/* Total */}
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-900">Total</span>
                <span className="text-xl font-bold text-indigo-600">
                  ${preview.totalCost.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Info */}
          <div className="flex items-start gap-2 text-xs text-slate-500 bg-blue-50 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-blue-700">What happens next:</p>
              <ul className="mt-1 space-y-0.5 text-blue-600">
                <li>• Domains will be purchased from the respective registrars</li>
                <li>• Nameservers will be automatically set to DNSimple</li>
                <li>• DNS propagation typically takes 24-48 hours</li>
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
          <Button onClick={handleConfirm} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Purchasing...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Confirm Purchase (${preview.totalCost.toFixed(2)})
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
