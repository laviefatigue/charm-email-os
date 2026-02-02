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
} from 'lucide-react';
import { toast } from 'sonner';
import { inboxProvisioningApi } from '@/lib/api';
import { formatDistanceToNow, format } from 'date-fns';

interface PurchaseJob {
  jobId: string;
  clientId: string;
  status: 'pending' | 'executing' | 'processing' | 'completed' | 'failed' | 'superseded' | 'cancelled';
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
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
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
        (j) => j.status === 'pending' || j.status === 'executing' || j.status === 'processing'
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="text-lg">Purchase Job History</CardTitle>
          <CardDescription>
            Track inbox provisioning jobs and retry failed purchases
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={fetchJobs} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
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
  );
}
