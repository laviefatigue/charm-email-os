'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
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
import { Progress } from '@/components/ui/progress';
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
  XCircle,
  RefreshCw,
  CreditCard,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import { inboxProvisioningApi } from '@/lib/api';
import type { SmartOrderPreview, InfrastructureType } from '@/lib/types';

// Job status types
type JobStatus = 'pending' | 'executing' | 'processing' | 'completed' | 'failed' | 'awaiting_checkout';

interface JobState {
  jobId: string;
  status: JobStatus;
  currentStep?: string;
  ordersCompleted: number;
  ordersTotal: number;
  totalInboxes: number;
  errors: string[];
  startedAt?: string;
  completedAt?: string;
  checkoutUrl?: string;
}

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

  // Job tracking state
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Calculate required domains for each provider
  const requiredDomains = providerType === 'entra' ? 2 : 5;
  const domainCount = selectedDomainIds.length;
  const canCreateOrder = domainCount >= requiredDomains && domainCount % requiredDomains === 0;

  // Cleanup polling on unmount or modal close
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      // Small delay to let the close animation finish
      setTimeout(() => {
        setJobState(null);
        setIsPolling(false);
        setError(null);
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }, 300);
    }
  }, [open]);

  // Load preview when modal opens or settings change
  useEffect(() => {
    if (open && selectedDomainIds.length > 0 && !jobState) {
      loadPreview();
    }
  }, [open, selectedDomainIds, providerType, customPurchase, jobState]);

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

  // Poll for job status
  const pollJobStatus = useCallback(async (jobId: string) => {
    try {
      const status = await inboxProvisioningApi.getJobStatus(jobId);

      setJobState({
        jobId: status.jobId,
        status: status.status as JobStatus,
        currentStep: status.currentStep,
        ordersCompleted: status.ordersCompleted,
        ordersTotal: status.ordersTotal,
        totalInboxes: status.totalInboxes,
        errors: status.errors || [],
        startedAt: status.startedAt,
        completedAt: status.completedAt,
        checkoutUrl: status.checkoutUrl,
      });

      // Stop polling if job is complete, failed, or awaiting manual checkout
      if (status.status === 'completed' || status.status === 'failed' || status.status === 'awaiting_checkout') {
        setIsPolling(false);
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }

        if (status.status === 'completed') {
          toast.success(`Successfully provisioned ${status.totalInboxes} inboxes!`);
          onSuccess();
        } else if (status.status === 'awaiting_checkout') {
          toast.info('Order submitted! Complete payment to finish.');
        } else {
          toast.error('Purchase failed. See details below.');
        }
      }
    } catch (err) {
      console.error('Failed to poll job status:', err);
      // Don't stop polling on error, might be transient
    }
  }, [onSuccess]);

  // Start polling for a job
  const startPolling = useCallback((jobId: string) => {
    setIsPolling(true);

    // Initial poll
    pollJobStatus(jobId);

    // Poll every 3 seconds
    pollingRef.current = setInterval(() => {
      pollJobStatus(jobId);
    }, 3000);
  }, [pollJobStatus]);

  const handleExecute = async () => {
    if (!preview || !preview.isValid) return;

    setIsExecuting(true);
    setError(null);

    try {
      const result = await inboxProvisioningApi.executeSmartOrder({
        clientId,
        domainIds: selectedDomainIds,
        providerType,
        overrideAgeCheck: hasAgeOverride,
        customPurchase,
      });

      // Initialize job state
      setJobState({
        jobId: result.jobId,
        status: 'pending',
        currentStep: 'Starting purchase...',
        ordersCompleted: 0,
        ordersTotal: preview.orderCount,
        totalInboxes: 0,
        errors: [],
      });

      // Start polling for status
      startPolling(result.jobId);

    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to execute order';
      setError(message);
      toast.error(message);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleRetry = () => {
    setJobState(null);
    setError(null);
    loadPreview();
  };

  const handleClose = () => {
    // Allow closing if not actively executing/polling, or if awaiting manual checkout
    if (!isExecuting && !isPolling) {
      onOpenChange(false);
    }
  };

  const getProviderIcon = (type: InfrastructureType) => {
    return type === 'entra' ? (
      <Cloud className="h-4 w-4 text-blue-600" />
    ) : (
      <Mail className="h-4 w-4 text-red-600" />
    );
  };

  const getStatusIcon = (status: JobStatus) => {
    switch (status) {
      case 'pending':
      case 'executing':
      case 'processing':
        return <Loader2 className="h-5 w-5 animate-spin text-blue-500" />;
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      case 'awaiting_checkout':
        return <CreditCard className="h-5 w-5 text-amber-500" />;
    }
  };

  const getStatusColor = (status: JobStatus) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'executing':
      case 'processing':
        return 'bg-blue-100 text-blue-800';
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'awaiting_checkout':
        return 'bg-amber-100 text-amber-800';
    }
  };

  // Render job progress view
  const renderJobProgress = () => {
    if (!jobState) return null;

    const progress = jobState.ordersTotal > 0
      ? (jobState.ordersCompleted / jobState.ordersTotal) * 100
      : 0;

    return (
      <div className="space-y-4">
        {/* Status header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {getStatusIcon(jobState.status)}
            <span className="font-medium">
              {jobState.status === 'pending' && 'Preparing...'}
              {(jobState.status === 'executing' || jobState.status === 'processing') && 'Processing...'}
              {jobState.status === 'completed' && 'Complete!'}
              {jobState.status === 'failed' && 'Failed'}
              {jobState.status === 'awaiting_checkout' && 'Awaiting Payment'}
            </span>
          </div>
          <Badge className={getStatusColor(jobState.status)}>
            {jobState.status}
          </Badge>
        </div>

        {/* Progress bar */}
        {(jobState.status === 'pending' || jobState.status === 'executing' || jobState.status === 'processing') && (
          <div className="space-y-2">
            <Progress value={progress} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{jobState.ordersCompleted} / {jobState.ordersTotal} orders</span>
              <span>{Math.round(progress)}%</span>
            </div>
          </div>
        )}

        {/* Current step */}
        {jobState.currentStep && (
          <div className="rounded-lg border bg-muted/30 p-3">
            <div className="flex items-center gap-2 text-sm">
              {(jobState.status === 'pending' || jobState.status === 'executing' || jobState.status === 'processing') && (
                <Loader2 className="h-3 w-3 animate-spin" />
              )}
              <span className="text-muted-foreground">{jobState.currentStep}</span>
            </div>
          </div>
        )}

        {/* Awaiting checkout - manual Stripe payment */}
        {jobState.status === 'awaiting_checkout' && (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center gap-2 text-amber-700">
                <CreditCard className="h-5 w-5" />
                <span className="font-medium">Payment Required</span>
              </div>
              <p className="text-sm text-amber-700">
                Order submitted successfully. Complete payment via Stripe to finish provisioning.
              </p>
              {jobState.checkoutUrl && (
                <Button
                  className="w-full"
                  onClick={() => window.open(jobState.checkoutUrl, '_blank')}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  Open Stripe Checkout
                </Button>
              )}
              <p className="text-xs text-muted-foreground">
                After payment, confirm via the Purchase Jobs table to complete the order.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Success details */}
        {jobState.status === 'completed' && (
          <Card className="border-green-200 bg-green-50">
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center gap-2 text-green-700">
                <CheckCircle2 className="h-5 w-5" />
                <span className="font-medium">Purchase Successful!</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Inboxes Created:</span>
                  <span className="ml-2 font-bold text-green-700">{jobState.totalInboxes}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Orders:</span>
                  <span className="ml-2 font-medium">{jobState.ordersCompleted}</span>
                </div>
              </div>
              {jobState.completedAt && (
                <div className="text-xs text-muted-foreground">
                  Completed at: {new Date(jobState.completedAt).toLocaleString()}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Failure details */}
        {jobState.status === 'failed' && (
          <Alert variant="destructive">
            <XCircle className="h-4 w-4" />
            <AlertTitle>Purchase Failed</AlertTitle>
            <AlertDescription>
              {jobState.errors.length > 0 ? (
                <ul className="list-disc list-inside mt-2 space-y-1">
                  {jobState.errors.map((err, i) => (
                    <li key={i} className="text-sm">{err}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2">An unknown error occurred. Please try again.</p>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* Job ID for reference */}
        <div className="text-xs text-muted-foreground">
          Job ID: <code className="bg-muted px-1 rounded">{jobState.jobId}</code>
        </div>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            {jobState ? 'Purchase Progress' : `Provision Inboxes for ${clientName}`}
          </DialogTitle>
          <DialogDescription>
            {jobState
              ? 'Tracking Hypertide automation progress'
              : 'Configure inbox provisioning via Hypertide'
            }
          </DialogDescription>
        </DialogHeader>

        {/* Show job progress if we have a job */}
        {jobState ? (
          renderJobProgress()
        ) : isLoading ? (
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
          {jobState ? (
            // Job in progress or complete - show appropriate buttons
            jobState.status === 'completed' ? (
              <Button onClick={() => onOpenChange(false)}>
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Done
              </Button>
            ) : jobState.status === 'failed' ? (
              <>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  Close
                </Button>
                <Button onClick={handleRetry}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Try Again
                </Button>
              </>
            ) : (
              // Still executing - show cancel warning
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Please wait while the purchase completes...
              </div>
            )
          ) : (
            // Preview mode - show cancel and execute buttons
            <>
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
                    Starting...
                  </>
                ) : (
                  <>
                    <Server className="h-4 w-4 mr-2" />
                    Confirm Purchase - ${preview?.monthlyCost ?? 0}/mo
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
