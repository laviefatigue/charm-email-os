'use client';

import { useState, useEffect, useCallback, useRef, Fragment } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
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
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RotateCcw,
  Eye,
  Server,
  Mail,
  AlertTriangle,
  Trash2,
  CreditCard,
  ShieldAlert,
  MessageSquare,
  Copy,
  UserCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import { inboxProvisioningApi } from '@/lib/api';
import { formatDistanceToNow, format } from 'date-fns';

interface PurchaseJob {
  jobId: string;
  clientId: string;
  status: 'pending' | 'executing' | 'processing' | 'completed' | 'failed' | 'awaiting_checkout' | 'superseded' | 'cancelled' | 'manual_processing';
  currentStep?: string;
  providerType: string;
  domainNames: string[];
  entraOrders: number;
  googleOrders: number;
  ordersCompleted: number;
  ordersTotal: number;
  totalInboxes: number;
  monthlyCost: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  errors?: string[];
  errorType?: 'payment' | 'config' | 'auth' | 'timeout' | 'system' | 'stale' | null;
  checkoutUrl?: string;
}

interface PurchaseJobsTableProps {
  clientId: string;
  onJobRetried?: () => void;
}

export function PurchaseJobsTable({ clientId, onJobRetried }: PurchaseJobsTableProps) {
  const [jobs, setJobs] = useState<PurchaseJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [confirmingJobId, setConfirmingJobId] = useState<string | null>(null);
  const [refreshingJobId, setRefreshingJobId] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [sendingToSlackJobId, setSendingToSlackJobId] = useState<string | null>(null);
  const [copyingOrderJobId, setCopyingOrderJobId] = useState<string | null>(null);
  const [manualCompletingJobId, setManualCompletingJobId] = useState<string | null>(null);
  const [showManualCompleteConfirm, setShowManualCompleteConfirm] = useState<string | null>(null);
  const [manualCompleteConfirmed, setManualCompleteConfirmed] = useState(false);
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;

  const fetchJobs = useCallback(async () => {
    try {
      const data = await inboxProvisioningApi.listJobs({ clientId });
      // listJobs() already returns camelCase via toCamelCase() in the API client
      const jobs = (data.jobs as unknown as PurchaseJob[]).map((j) => ({
        ...j,
        domainNames: j.domainNames || [],
        errors: j.errors || [],
      }));
      setJobs(jobs);
    } catch (err) {
      console.error('Failed to load job history:', err);
      toast.error('Failed to load job history');
    } finally {
      setIsLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    fetchJobs();
    // Poll for updates every 10 seconds if any jobs are pending/executing
    const interval = setInterval(() => {
      const hasActiveJobs = jobsRef.current.some(
        (j) => j.status === 'pending' || j.status === 'executing' || j.status === 'processing' || j.status === 'awaiting_checkout'
      );
      if (hasActiveJobs) {
        fetchJobs();
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const handleRetry = async (jobId: string) => {
    setRetryingJobId(jobId);
    try {
      await inboxProvisioningApi.retryJob(jobId);
      toast.success('Job retry started');
      fetchJobs();
      onJobRetried?.();
    } catch (err) {
      console.error('Failed to retry job:', err);
      toast.error('Failed to retry job');
    } finally {
      setRetryingJobId(null);
    }
  };

  const handleCancel = useCallback(async (jobId: string) => {
    try {
      setCancellingJobId(jobId);
      await inboxProvisioningApi.cancelJob(jobId);
      toast.success('Job cancelled, domains unlocked');
      fetchJobs();
      onJobRetried?.();
    } catch (err: any) {
      toast.error(err.message || 'Failed to cancel job');
    } finally {
      setCancellingJobId(null);
    }
  }, [fetchJobs, onJobRetried]);

  const handleConfirmCheckout = useCallback(async (jobId: string) => {
    try {
      setConfirmingJobId(jobId);
      await inboxProvisioningApi.confirmCheckout(jobId);
      toast.success('Payment confirmed! Job marked as completed.');
      fetchJobs();
      onJobRetried?.();
    } catch (err: any) {
      toast.error(err.message || 'Failed to confirm checkout');
    } finally {
      setConfirmingJobId(null);
    }
  }, [fetchJobs, onJobRetried]);

  const handleRefreshJob = useCallback(async (jobId: string) => {
    setRefreshingJobId(jobId);
    try {
      const updated = await inboxProvisioningApi.getJobStatus(jobId);
      setJobs(prev => prev.map(j =>
        j.jobId === jobId ? { ...j, ...updated } as PurchaseJob : j
      ));
    } catch (err) {
      console.error('Failed to refresh job:', err);
      toast.error('Failed to refresh job status');
    } finally {
      setRefreshingJobId(null);
    }
  }, []);

  const handleSendToSlack = useCallback(async (jobId: string) => {
    setSendingToSlackJobId(jobId);
    try {
      const result = await inboxProvisioningApi.sendToSlack(jobId);
      toast.success(`Order sent to ${result.channel}`);
      fetchJobs();
    } catch (err: any) {
      console.error('Failed to send to Slack:', err);
      toast.error(err.message || 'Failed to send to Slack');
    } finally {
      setSendingToSlackJobId(null);
    }
  }, [fetchJobs]);

  const handleCopyOrder = useCallback(async (jobId: string) => {
    setCopyingOrderJobId(jobId);
    try {
      const result = await inboxProvisioningApi.getOrderSummary(jobId);
      await navigator.clipboard.writeText(result.summary);
      toast.success('Order details copied to clipboard');
    } catch (err: any) {
      console.error('Failed to copy order:', err);
      toast.error(err.message || 'Failed to copy order details');
    } finally {
      setCopyingOrderJobId(null);
    }
  }, []);

  const handleManualComplete = useCallback(async (jobId: string) => {
    setManualCompletingJobId(jobId);
    try {
      await inboxProvisioningApi.manualComplete(jobId);
      toast.success('Job marked as manually completed');
      setShowManualCompleteConfirm(null);
      setManualCompleteConfirmed(false);
      fetchJobs();
      onJobRetried?.();
    } catch (err: any) {
      console.error('Failed to complete job:', err);
      toast.error(err.message || 'Failed to mark job as complete');
    } finally {
      setManualCompletingJobId(null);
    }
  }, [fetchJobs, onJobRetried]);

  const getFailureBadge = (errorType?: string | null) => {
    switch (errorType) {
      case 'payment':
        return (
          <Badge variant="destructive" className="gap-1">
            <CreditCard className="h-3 w-3" />
            Payment Failed
          </Badge>
        );
      case 'config':
        return (
          <Badge className="bg-orange-100 text-orange-800 gap-1">
            <AlertTriangle className="h-3 w-3" />
            Config Error
          </Badge>
        );
      case 'auth':
        return (
          <Badge className="bg-yellow-100 text-yellow-800 gap-1">
            <ShieldAlert className="h-3 w-3" />
            Auth Error
          </Badge>
        );
      case 'timeout':
        return (
          <Badge variant="secondary" className="gap-1">
            <Clock className="h-3 w-3" />
            Timed Out
          </Badge>
        );
      case 'stale':
        return (
          <Badge variant="secondary" className="gap-1">
            <AlertTriangle className="h-3 w-3" />
            Stale (Crashed)
          </Badge>
        );
      case 'system':
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            System Error
          </Badge>
        );
      default:
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            Failed
          </Badge>
        );
    }
  };

  const getStatusBadge = (job: PurchaseJob) => {
    switch (job.status) {
      case 'pending':
        return (
          <Badge variant="outline" className="gap-1">
            <Clock className="h-3 w-3" />
            Pending
          </Badge>
        );
      case 'executing':
      case 'processing':
        return (
          <Badge className="bg-blue-100 text-blue-800 gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            Running
          </Badge>
        );
      case 'completed':
        return (
          <Badge className="bg-green-100 text-green-800 gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Completed
          </Badge>
        );
      case 'failed':
        return getFailureBadge(job.errorType);
      case 'awaiting_checkout':
        return (
          <Badge className="bg-amber-100 text-amber-800 gap-1">
            <CreditCard className="h-3 w-3" />
            Awaiting Payment
          </Badge>
        );
      case 'superseded':
        return (
          <Badge variant="secondary" className="gap-1">
            <RotateCcw className="h-3 w-3" />
            Superseded
          </Badge>
        );
      case 'cancelled':
        return (
          <Badge variant="secondary" className="gap-1">
            <XCircle className="h-3 w-3" />
            Cancelled
          </Badge>
        );
      case 'manual_processing':
        return (
          <Badge variant="outline" className="bg-purple-50 text-purple-700 gap-1">
            <Clock className="h-3 w-3" />
            Manual Processing
          </Badge>
        );
      default:
        return <Badge>{job.status}</Badge>;
    }
  };

  const getProviderBadge = (providerType: string) => {
    if (providerType === 'entra' || providerType === 'mixed') {
      return (
        <Badge variant="outline" className="gap-1 bg-blue-50">
          <Server className="h-3 w-3 text-blue-600" />
          {providerType === 'mixed' ? 'Mixed' : 'Entra'}
        </Badge>
      );
    } else if (providerType === 'google') {
      return (
        <Badge variant="outline" className="gap-1 bg-red-50">
          <Mail className="h-3 w-3 text-red-600" />
          Google
        </Badge>
      );
    }
    return <Badge variant="outline">{providerType || 'Unknown'}</Badge>;
  };

  const formatDuration = (job: PurchaseJob) => {
    if (job.completedAt && job.startedAt) {
      const start = new Date(job.startedAt).getTime();
      const end = new Date(job.completedAt).getTime();
      const seconds = Math.round((end - start) / 1000);
      if (seconds < 60) return `${seconds}s`;
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return `${minutes}m ${remainingSeconds}s`;
    }
    if (job.status === 'executing' || job.status === 'processing') {
      return <Loader2 className="h-4 w-4 animate-spin" />;
    }
    return '-';
  };

  return (
    <>
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Purchase Job History</CardTitle>
        <CardDescription>
          Track inbox provisioning jobs and retry failed purchases
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && jobs.length === 0 ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Mail className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>No purchase jobs yet.</p>
            <p className="text-sm">
              Use the &quot;Setup Inboxes&quot; button to provision new inboxes.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
          <Table className="table-fixed w-full">
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Domains</TableHead>
                <TableHead>Inboxes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <Fragment key={job.jobId}>
                  <TableRow
                    className={expandedJobId === job.jobId ? 'border-b-0' : ''}
                  >
                    <TableCell>{getStatusBadge(job)}</TableCell>
                    <TableCell>{getProviderBadge(job.providerType)}</TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-help">
                              {job.domainNames?.length || 0} domain(s)
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            <div className="max-w-xs">
                              {job.domainNames?.length > 0
                                ? job.domainNames.slice(0, 5).join(', ') +
                                  (job.domainNames.length > 5
                                    ? ` +${job.domainNames.length - 5} more`
                                    : '')
                                : 'No domains'}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Mail className="h-3 w-3 text-muted-foreground" />
                        {job.totalInboxes || '-'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-help text-sm">
                              {job.createdAt
                                ? formatDistanceToNow(new Date(job.createdAt), {
                                    addSuffix: true,
                                  })
                                : '-'}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {job.createdAt
                              ? format(new Date(job.createdAt), 'PPpp')
                              : 'Unknown'}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                    <TableCell>{formatDuration(job)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {job.status === 'awaiting_checkout' && job.checkoutUrl && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => window.open(job.checkoutUrl, '_blank')}
                                  className="text-amber-700 hover:text-amber-800 hover:bg-amber-50"
                                >
                                  <CreditCard className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Open Stripe checkout to pay</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {job.status === 'awaiting_checkout' && (
                          <>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleConfirmCheckout(job.jobId)}
                                    disabled={confirmingJobId === job.jobId}
                                    className="text-green-600 hover:text-green-700 hover:bg-green-50"
                                  >
                                    {confirmingJobId === job.jobId ? (
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <CheckCircle2 className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Confirm payment completed</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCancel(job.jobId)}
                                    disabled={cancellingJobId === job.jobId}
                                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                  >
                                    {cancellingJobId === job.jobId ? (
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <Trash2 className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Cancel job &amp; unlock domains</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </>
                        )}
                        {(job.status === 'failed' || job.status === 'pending') && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleCancel(job.jobId)}
                                  disabled={cancellingJobId === job.jobId}
                                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                >
                                  {cancellingJobId === job.jobId ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Trash2 className="h-4 w-4" />
                                  )}
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Cancel job &amp; unlock domains</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {/* Failed jobs auto-notify Slack, so only show Retry here */}
                        {job.status === 'failed' && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleRetry(job.jobId)}
                                  disabled={retryingJobId === job.jobId}
                                >
                                  {retryingJobId === job.jobId ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <RotateCcw className="h-4 w-4" />
                                  )}
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Retry this job</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {job.status === 'manual_processing' && (
                          <>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCopyOrder(job.jobId)}
                                    disabled={copyingOrderJobId === job.jobId}
                                  >
                                    {copyingOrderJobId === job.jobId ? (
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <Copy className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Copy order details</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCancel(job.jobId)}
                                    disabled={cancellingJobId === job.jobId}
                                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                                  >
                                    {cancellingJobId === job.jobId ? (
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <Trash2 className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Delete job &amp; unlock domains</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </>
                        )}
                        {(job.status === 'failed' || job.status === 'manual_processing') && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    setShowManualCompleteConfirm(job.jobId);
                                    setManualCompleteConfirmed(false);
                                  }}
                                  className="text-green-600 hover:text-green-700 hover:bg-green-50"
                                >
                                  <UserCheck className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Mark as manually completed</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRefreshJob(job.jobId)}
                                disabled={refreshingJobId === job.jobId}
                              >
                                {refreshingJobId === job.jobId ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <RefreshCw className="h-4 w-4" />
                                )}
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Refresh status</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setExpandedJobId(
                                    expandedJobId === job.jobId ? null : job.jobId
                                  )
                                }
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </TableCell>
                  </TableRow>
                  {/* Expanded details row */}
                  {expandedJobId === job.jobId && (
                    <TableRow key={`${job.jobId}-details`}>
                      <TableCell colSpan={7} className="bg-muted/50 p-4 max-w-0">
                        <div className="space-y-3 text-sm whitespace-normal wrap-break-word overflow-hidden">
                          {job.currentStep && (
                            <div>
                              <span className="font-medium">Current Step:</span>{' '}
                              {job.currentStep}
                            </div>
                          )}
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <span className="font-medium">Orders:</span>{' '}
                              {job.ordersCompleted}/{job.ordersTotal} completed
                            </div>
                            <div>
                              <span className="font-medium">Cost:</span> $
                              {job.monthlyCost?.toFixed(2) || '0.00'}/mo
                            </div>
                          </div>
                          {job.domainNames && job.domainNames.length > 0 && (
                            <div>
                              <span className="font-medium">Domains:</span>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {job.domainNames.map((domain) => (
                                  <Badge
                                    key={domain}
                                    variant="outline"
                                    className="text-xs"
                                  >
                                    {domain}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}
                          {job.status === 'awaiting_checkout' && job.checkoutUrl && (
                            <div className="bg-amber-50 border border-amber-200 rounded p-3">
                              <div className="flex items-center gap-2 text-amber-700 font-medium mb-2">
                                <CreditCard className="h-4 w-4" />
                                Manual Checkout Required
                              </div>
                              <p className="text-amber-600 text-xs mb-2">
                                Automation completed all steps. Click the link below to complete payment in your browser, then click &quot;Confirm&quot;.
                              </p>
                              <a
                                href={job.checkoutUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-amber-800 underline text-xs break-all hover:text-amber-900"
                              >
                                {job.checkoutUrl}
                              </a>
                            </div>
                          )}
                          {job.errors && job.errors.length > 0 && (
                            <div className="bg-red-50 border border-red-200 rounded p-3">
                              <div className="flex items-center gap-2 text-red-700 font-medium mb-2">
                                <AlertTriangle className="h-4 w-4" />
                                Errors
                              </div>
                              <ul className="list-disc list-inside text-red-600 text-xs space-y-1 wrap-break-word">
                                {job.errors.map((error, idx) => (
                                  <li key={idx}>{error}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
          </div>
        )}
      </CardContent>
    </Card>

    {/* Manual Complete Confirmation Dialog */}
    <Dialog
      open={!!showManualCompleteConfirm}
      onOpenChange={(open) => {
        if (!open) {
          setShowManualCompleteConfirm(null);
          setManualCompleteConfirmed(false);
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirm Manual Completion</DialogTitle>
          <DialogDescription>
            Marking this job as complete will update all associated domains to &quot;active&quot; status with the appropriate infrastructure type.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-start space-x-3 py-4">
          <Checkbox
            id="confirm-manual-complete"
            checked={manualCompleteConfirmed}
            onCheckedChange={(checked) => setManualCompleteConfirmed(!!checked)}
          />
          <Label htmlFor="confirm-manual-complete" className="text-sm leading-relaxed cursor-pointer">
            I confirm this order was processed manually in Hypertide and all inboxes have been created successfully.
          </Label>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setShowManualCompleteConfirm(null);
              setManualCompleteConfirmed(false);
            }}
          >
            Cancel
          </Button>
          <Button
            onClick={() => showManualCompleteConfirm && handleManualComplete(showManualCompleteConfirm)}
            disabled={!manualCompleteConfirmed || manualCompletingJobId !== null}
            className="bg-green-600 hover:bg-green-700"
          >
            {manualCompletingJobId ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <CheckCircle2 className="h-4 w-4 mr-2" />
            )}
            Mark Complete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
