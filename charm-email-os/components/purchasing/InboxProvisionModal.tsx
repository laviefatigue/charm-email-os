'use client';

import { useState, useEffect } from 'react';
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
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Cloud,
  Mail,
  User,
  Globe,
  Server,
  Package,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { inboxProvisioningApi } from '@/lib/api';
import type { SmartOrderPreview, InfrastructureType } from '@/lib/types';

interface InboxProvisionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  selectedDomainIds: string[];
  hasAgeOverride?: boolean;  // True if any selected domain was force-selected (admin override for <30 day age)
  onSuccess: () => void;
}

export function InboxProvisionModal({
  open,
  onOpenChange,
  clientId,
  clientName,
  selectedDomainIds,
  hasAgeOverride = false,
  onSuccess,
}: InboxProvisionModalProps) {
  const [preview, setPreview] = useState<SmartOrderPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [providerType, setProviderType] = useState<InfrastructureType>('entra');
  const [customPurchase, setCustomPurchase] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Calculate required domains for each provider
  const requiredDomains = providerType === 'entra' ? 2 : 5;
  const domainCount = selectedDomainIds.length;
  const canCreateOrder = domainCount >= requiredDomains && domainCount % requiredDomains === 0;
  const ordersFromDomains = Math.floor(domainCount / requiredDomains);

  // Load preview when modal opens or settings change
  useEffect(() => {
    if (open && selectedDomainIds.length > 0) {
      loadPreview();
    }
  }, [open, selectedDomainIds, providerType, customPurchase]);

  const loadPreview = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await inboxProvisioningApi.getSmartOrderPreview(
        clientId,
        selectedDomainIds,
        providerType,
        customPurchase
      );
      setPreview(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load preview';
      setError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleExecute = async () => {
    if (!preview || !preview.isValid) return;

    setIsExecuting(true);
    try {
      const result = await inboxProvisioningApi.executeSmartOrder({
        clientId,
        domainIds: selectedDomainIds,
        providerType,
        overrideAgeCheck: hasAgeOverride,
        customPurchase,
      });

      toast.success(`Purchase started! Job ID: ${result.jobId}`);
      onSuccess();
      onOpenChange(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to execute order';
      toast.error(message);
    } finally {
      setIsExecuting(false);
    }
  };

  const getProviderIcon = (type: InfrastructureType) => {
    return type === 'entra' ? (
      <Cloud className="h-4 w-4 text-blue-600" />
    ) : (
      <Mail className="h-4 w-4 text-red-600" />
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Provision Inboxes for {clientName}
          </DialogTitle>
          <DialogDescription>
            Configure inbox provisioning via Hypertide
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : preview ? (
          <div className="space-y-4">
            {/* Auto-configured section */}
            <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                Auto-configured from your settings
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="flex items-center gap-2">
                  <User className="h-3 w-3 text-muted-foreground" />
                  <span className="text-muted-foreground">Sender:</span>
                  <span className="font-medium">
                    {preview.senderName.firstName} {preview.senderName.lastName}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Package className="h-3 w-3 text-muted-foreground" />
                  <span className="text-muted-foreground">Prefixes:</span>
                  <span className="font-medium">{preview.senderName.prefixCount} ready</span>
                </div>
                {preview.forwardingDomain && (
                  <div className="flex items-center gap-2 col-span-2">
                    <Globe className="h-3 w-3 text-muted-foreground" />
                    <span className="text-muted-foreground">Forwarding:</span>
                    <span className="font-medium">{preview.forwardingDomain}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Provider selection */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Infrastructure Provider</label>
              <Select
                value={providerType}
                onValueChange={(value) => setProviderType(value as InfrastructureType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="entra">
                    <div className="flex items-center gap-2">
                      <Cloud className="h-4 w-4 text-blue-600" />
                      <span>Entra (Microsoft 365)</span>
                      <span className="text-muted-foreground">- 50 inboxes/domain</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="google">
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-red-600" />
                      <span>Google Workspace</span>
                      <span className="text-muted-foreground">- 3 inboxes/domain</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Custom Purchase Toggle */}
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/20">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-amber-500" />
                  <Label htmlFor="custom-purchase" className="font-medium">
                    Custom Purchase
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  Bypass package limits. Requires {requiredDomains} domains per {providerType === 'entra' ? 'Entra' : 'Google'} order.
                </p>
              </div>
              <Switch
                id="custom-purchase"
                checked={customPurchase}
                onCheckedChange={setCustomPurchase}
              />
            </div>

            {/* Domain count validation for custom purchase */}
            {customPurchase && !canCreateOrder && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Invalid domain count</AlertTitle>
                <AlertDescription>
                  {providerType === 'entra'
                    ? `Entra requires exactly 2 domains per order. You have ${domainCount} selected.`
                    : `Google requires exactly 5 domains per order. You have ${domainCount} selected.`
                  }
                  {domainCount > 0 && domainCount < requiredDomains && (
                    <> Select {requiredDomains - domainCount} more domain{requiredDomains - domainCount > 1 ? 's' : ''}.</>
                  )}
                  {domainCount > requiredDomains && domainCount % requiredDomains !== 0 && (
                    <> Select {requiredDomains - (domainCount % requiredDomains)} more or deselect {domainCount % requiredDomains} domain{(domainCount % requiredDomains) > 1 ? 's' : ''}.</>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {/* Order summary */}
            <Card>
              <CardContent className="pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Provider</span>
                  <div className="flex items-center gap-2">
                    {getProviderIcon(preview.providerType as InfrastructureType)}
                    <span className="font-medium capitalize">{preview.providerType}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Domains</span>
                  <span className="font-medium">{preview.domains.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Orders</span>
                  <span className="font-medium">{preview.orderCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Total Inboxes</span>
                  <Badge variant="secondary" className="text-base">
                    {preview.inboxCount}
                  </Badge>
                </div>
                <div className="border-t pt-3 flex items-center justify-between">
                  <span className="text-sm font-medium">Monthly Cost</span>
                  <span className="text-lg font-bold text-green-600">
                    ${preview.monthlyCost}/mo
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Package usage */}
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {customPurchase ? 'Purchase Mode' : 'Package Usage'}
              </span>
              {customPurchase ? (
                <span className="text-amber-600 font-medium flex items-center gap-1">
                  <Zap className="h-3 w-3" />
                  Custom (no package)
                </span>
              ) : (
                <span
                  className={
                    preview.packageUsage.withinLimit
                      ? 'text-green-600'
                      : 'text-red-600 font-medium'
                  }
                >
                  {preview.packageUsage.used} / {preview.packageUsage.available} orders used
                  {!preview.packageUsage.withinLimit && ' (limit exceeded)'}
                </span>
              )}
            </div>

            {/* Domain list */}
            <div className="space-y-1">
              <span className="text-sm font-medium">Domains to provision:</span>
              <div className="flex flex-wrap gap-1">
                {preview.domains.map((domain) => (
                  <Badge key={domain} variant="outline" className="text-xs">
                    {domain}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Validation errors */}
            {preview.validationErrors.length > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Cannot proceed</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc list-inside">
                    {preview.validationErrors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleExecute}
            disabled={
              isLoading ||
              isExecuting ||
              (customPurchase ? !canCreateOrder : !preview?.isValid)
            }
            className="bg-orange-600 hover:bg-orange-700"
          >
            {isExecuting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Server className="h-4 w-4 mr-2" />
                Confirm Purchase - ${preview?.monthlyCost ?? 0}/mo
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
