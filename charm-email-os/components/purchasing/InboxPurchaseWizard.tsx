'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Mail,
  ArrowLeft,
  ArrowRight,
  Loader2,
  Check,
  X,
  DollarSign,
  AlertTriangle,
  Users,
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// Types
interface Domain {
  id: string;
  domainName: string;
  status: string;
  inboxCount?: number;
}

interface InboxName {
  firstName: string;
  lastName: string;
  emailPrefix: string;
}

interface OrderBreakdown {
  entraOrders: number;
  entraDomains: number;
  entraInboxesActual: number;
  googleOrders: number;
  googleDomains: number;
  googleInboxesActual: number;
  totalOrders: number;
  totalInboxes: number;
  totalDomains: number;
  totalMonthlyCapacity: number;
  estimatedMonthlyCost: number;
  hasEntra: boolean;
  hasGoogle: boolean;
  isMixed: boolean;
}

interface JobStatus {
  jobId: string;
  status: 'pending' | 'calculating' | 'ready' | 'executing' | 'completed' | 'failed';
  currentStep?: string;
  ordersCompleted: number;
  ordersTotal: number;
  totalInboxes: number;
  errors: string[];
}

interface InboxPurchaseWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  forwardingDomain: string;
  domains: Domain[];
  onComplete?: (totalInboxes: number) => void;
}

type WizardStep = 'configure' | 'names' | 'review' | 'execute';

const WIZARD_STEPS: { key: WizardStep; label: string; description: string }[] = [
  { key: 'configure', label: 'Configure', description: 'Set inbox targets' },
  { key: 'names', label: 'Names', description: 'Generate inbox names' },
  { key: 'review', label: 'Review', description: 'Review order' },
  { key: 'execute', label: 'Execute', description: 'Run automation' },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export function InboxPurchaseWizard({
  open,
  onOpenChange,
  clientId,
  clientName,
  forwardingDomain,
  domains,
  onComplete,
}: InboxPurchaseWizardProps) {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('configure');
  const [isLoading, setIsLoading] = useState(false);

  // Configuration state
  const [entraInboxes, setEntraInboxes] = useState(100);
  const [googleInboxes, setGoogleInboxes] = useState(0);
  const [orderBreakdown, setOrderBreakdown] = useState<OrderBreakdown | null>(null);
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);

  // Names state
  const [inboxNames, setInboxNames] = useState<InboxName[]>([]);
  const [customFirstName, setCustomFirstName] = useState('');
  const [customLastName, setCustomLastName] = useState('');

  // Execution state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  // Get current step index
  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  // Navigation
  const goBack = () => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      setCurrentStep(WIZARD_STEPS[prevIndex].key);
    }
  };

  const goNext = () => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < WIZARD_STEPS.length) {
      setCurrentStep(WIZARD_STEPS[nextIndex].key);
    }
  };

  // Calculate order breakdown
  const handleCalculate = useCallback(async () => {
    if (entraInboxes === 0 && googleInboxes === 0) {
      toast.error('Set at least one inbox target');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/inbox-purchasing/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          inbox_target: {
            entra_inboxes: entraInboxes,
            google_inboxes: googleInboxes,
          },
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to calculate orders');
      }

      const data = await response.json();
      setOrderBreakdown({
        entraOrders: data.breakdown.entra_orders,
        entraDomains: data.breakdown.entra_domains,
        entraInboxesActual: data.breakdown.entra_inboxes_actual,
        googleOrders: data.breakdown.google_orders,
        googleDomains: data.breakdown.google_domains,
        googleInboxesActual: data.breakdown.google_inboxes_actual,
        totalOrders: data.breakdown.total_orders,
        totalInboxes: data.breakdown.total_inboxes,
        totalDomains: data.breakdown.total_domains,
        totalMonthlyCapacity: data.breakdown.total_monthly_capacity,
        estimatedMonthlyCost: data.breakdown.estimated_monthly_cost,
        hasEntra: data.breakdown.has_entra,
        hasGoogle: data.breakdown.has_google,
        isMixed: data.breakdown.is_mixed,
      });
      toast.success('Order calculated');
    } catch (error: any) {
      toast.error(error.message || 'Failed to calculate');
    } finally {
      setIsLoading(false);
    }
  }, [clientId, entraInboxes, googleInboxes]);

  // Generate inbox names
  const handleGenerateNames = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/inbox-purchasing/generate-names`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          count: Math.min(10, orderBreakdown?.totalInboxes || 10),
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate names');
      }

      const data = await response.json();
      setInboxNames(
        data.names.map((n: any) => ({
          firstName: n.first_name,
          lastName: n.last_name,
          emailPrefix: n.email_prefix,
        }))
      );
      toast.success(`Generated ${data.count} inbox names`);
    } catch (error: any) {
      toast.error(error.message || 'Failed to generate names');
    } finally {
      setIsLoading(false);
    }
  }, [clientId, orderBreakdown]);

  // Add custom name
  const addCustomName = () => {
    if (!customFirstName.trim() || !customLastName.trim()) {
      toast.error('Enter both first and last name');
      return;
    }
    if (inboxNames.length >= 10) {
      toast.error('Maximum 10 names allowed');
      return;
    }

    const firstName = customFirstName.trim();
    const lastName = customLastName.trim();
    const emailPrefix = `${firstName.toLowerCase()}.${lastName.toLowerCase()}`;

    if (inboxNames.some((n) => n.emailPrefix === emailPrefix)) {
      toast.error('This name combination already exists');
      return;
    }

    setInboxNames((prev) => [...prev, { firstName, lastName, emailPrefix }]);
    setCustomFirstName('');
    setCustomLastName('');
  };

  // Remove name
  const removeName = (emailPrefix: string) => {
    setInboxNames((prev) => prev.filter((n) => n.emailPrefix !== emailPrefix));
  };

  // Execute purchase
  const handleExecutePurchase = useCallback(async () => {
    if (!orderBreakdown) {
      toast.error('Calculate order first');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/inbox-purchasing/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          client_name: clientName,
          forwarding_domain: forwardingDomain,
          inbox_target: {
            entra_inboxes: entraInboxes,
            google_inboxes: googleInboxes,
          },
          inbox_names: inboxNames.map((n) => ({
            first_name: n.firstName,
            last_name: n.lastName,
          })),
          use_saved_payment: true,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start purchase');
      }

      const data = await response.json();
      setJobId(data.job_id);
      setJobStatus({
        jobId: data.job_id,
        status: data.status,
        currentStep: 'Initializing...',
        ordersCompleted: 0,
        ordersTotal: orderBreakdown.totalOrders,
        totalInboxes: 0,
        errors: [],
      });

      // Start polling for status
      const interval = setInterval(() => pollJobStatus(data.job_id), 3000);
      setPollingInterval(interval);

      toast.success('Purchase job started');
      goNext();
    } catch (error: any) {
      toast.error(error.message || 'Failed to start purchase');
    } finally {
      setIsLoading(false);
    }
  }, [clientId, clientName, forwardingDomain, entraInboxes, googleInboxes, inboxNames, orderBreakdown]);

  // Poll job status
  const pollJobStatus = async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/inbox-purchasing/status/${id}`);
      if (!response.ok) {
        throw new Error('Failed to fetch status');
      }

      const data = await response.json();
      setJobStatus({
        jobId: data.job_id,
        status: data.status,
        currentStep: data.current_step,
        ordersCompleted: data.orders_completed,
        ordersTotal: data.orders_total,
        totalInboxes: data.total_inboxes,
        errors: data.errors || [],
      });

      // Stop polling if completed or failed
      if (data.status === 'completed' || data.status === 'failed') {
        if (pollingInterval) {
          clearInterval(pollingInterval);
          setPollingInterval(null);
        }

        if (data.status === 'completed') {
          toast.success(`Successfully created ${data.total_inboxes} inboxes!`);
          onComplete?.(data.total_inboxes);
        } else {
          toast.error('Purchase failed. Check errors for details.');
        }
      }
    } catch (error) {
      console.error('Failed to poll job status:', error);
    }
  };

  // Toggle domain selection
  const toggleDomain = (domainId: string) => {
    setSelectedDomains((prev) =>
      prev.includes(domainId)
        ? prev.filter((id) => id !== domainId)
        : [...prev, domainId]
    );
  };

  // Get job progress percentage
  const getProgressPercentage = () => {
    if (!jobStatus) return 0;
    switch (jobStatus.status) {
      case 'pending':
        return 10;
      case 'calculating':
        return 20;
      case 'ready':
        return 30;
      case 'executing':
        return 30 + (jobStatus.ordersCompleted / Math.max(jobStatus.ordersTotal, 1)) * 60;
      case 'completed':
        return 100;
      case 'failed':
        return 100;
      default:
        return 0;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Inbox Purchase Wizard
          </DialogTitle>
          <DialogDescription>
            Purchase inboxes from HyperTide (Entra or Google)
          </DialogDescription>
        </DialogHeader>

        {/* Step Indicator */}
        <div className="flex items-center justify-between mb-6">
          {WIZARD_STEPS.map((step, index) => (
            <div key={step.key} className="flex items-center">
              <div
                className={cn(
                  'flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium',
                  index < currentStepIndex
                    ? 'bg-primary text-primary-foreground'
                    : index === currentStepIndex
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
                )}
              >
                {index < currentStepIndex ? (
                  <Check className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </div>
              <div className="ml-2 hidden sm:block">
                <p className="text-sm font-medium">{step.label}</p>
                <p className="text-xs text-muted-foreground">{step.description}</p>
              </div>
              {index < WIZARD_STEPS.length - 1 && (
                <div
                  className={cn(
                    'w-12 h-0.5 mx-2',
                    index < currentStepIndex ? 'bg-primary' : 'bg-muted'
                  )}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="min-h-[400px]">
          {currentStep === 'configure' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Inbox Targets</CardTitle>
                  <CardDescription>
                    Set how many inboxes you need for {clientName}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Entra Inboxes */}
                  <div className="space-y-2">
                    <Label>Entra (Microsoft) Inboxes</Label>
                    <Input
                      type="number"
                      value={entraInboxes}
                      onChange={(e) => setEntraInboxes(Math.max(0, parseInt(e.target.value) || 0))}
                      step={100}
                      min={0}
                    />
                    <p className="text-xs text-muted-foreground">
                      100 inboxes per order (2 domains × 50 inboxes). $50/mo per order.
                    </p>
                  </div>

                  {/* Google Inboxes */}
                  <div className="space-y-2">
                    <Label>Google Workspace Inboxes</Label>
                    <Input
                      type="number"
                      value={googleInboxes}
                      onChange={(e) => setGoogleInboxes(Math.max(0, parseInt(e.target.value) || 0))}
                      step={15}
                      min={0}
                    />
                    <p className="text-xs text-muted-foreground">
                      15 inboxes per order (5 domains × 3 inboxes). $50/mo per order.
                    </p>
                  </div>

                  <Button onClick={handleCalculate} disabled={isLoading}>
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4 mr-2" />
                    )}
                    Calculate Order
                  </Button>
                </CardContent>
              </Card>

              {/* Order Breakdown */}
              {orderBreakdown && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Order Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.totalOrders}</div>
                        <div className="text-xs text-muted-foreground">Total Orders</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.totalInboxes}</div>
                        <div className="text-xs text-muted-foreground">Total Inboxes</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.totalDomains}</div>
                        <div className="text-xs text-muted-foreground">Total Domains</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold text-green-600">
                          ${orderBreakdown.estimatedMonthlyCost}
                        </div>
                        <div className="text-xs text-muted-foreground">Monthly Cost</div>
                      </div>
                    </div>

                    {orderBreakdown.isMixed && (
                      <Alert>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>
                          Mixed order: {orderBreakdown.entraOrders} Entra order(s) + {orderBreakdown.googleOrders} Google order(s).
                          HyperTide will process these sequentially.
                        </AlertDescription>
                      </Alert>
                    )}

                    <div className="grid grid-cols-2 gap-4 mt-4">
                      {orderBreakdown.hasEntra && (
                        <div className="p-3 border rounded-lg">
                          <div className="font-medium flex items-center gap-2">
                            <Badge variant="outline">Entra</Badge>
                          </div>
                          <div className="text-sm text-muted-foreground mt-2">
                            <p>{orderBreakdown.entraOrders} order(s)</p>
                            <p>{orderBreakdown.entraDomains} domains</p>
                            <p>{orderBreakdown.entraInboxesActual} inboxes</p>
                          </div>
                        </div>
                      )}
                      {orderBreakdown.hasGoogle && (
                        <div className="p-3 border rounded-lg">
                          <div className="font-medium flex items-center gap-2">
                            <Badge variant="outline">Google</Badge>
                          </div>
                          <div className="text-sm text-muted-foreground mt-2">
                            <p>{orderBreakdown.googleOrders} order(s)</p>
                            <p>{orderBreakdown.googleDomains} domains</p>
                            <p>{orderBreakdown.googleInboxesActual} inboxes</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {currentStep === 'names' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Inbox Names</CardTitle>
                  <CardDescription>
                    Configure names for inbox accounts (first.last@domain.com)
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Generate Button */}
                  <div className="flex gap-2">
                    <Button onClick={handleGenerateNames} disabled={isLoading}>
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Users className="h-4 w-4 mr-2" />
                      )}
                      Generate Random Names
                    </Button>
                  </div>

                  {/* Custom Name Input */}
                  <div className="flex gap-2">
                    <Input
                      placeholder="First name"
                      value={customFirstName}
                      onChange={(e) => setCustomFirstName(e.target.value)}
                    />
                    <Input
                      placeholder="Last name"
                      value={customLastName}
                      onChange={(e) => setCustomLastName(e.target.value)}
                    />
                    <Button variant="outline" onClick={addCustomName}>
                      Add
                    </Button>
                  </div>

                  {/* Names List */}
                  {inboxNames.length > 0 && (
                    <div className="space-y-2">
                      <Label>Names ({inboxNames.length}/10)</Label>
                      <div className="flex flex-wrap gap-2">
                        {inboxNames.map((name) => (
                          <Badge
                            key={name.emailPrefix}
                            variant="secondary"
                            className="cursor-pointer hover:bg-destructive hover:text-destructive-foreground"
                            onClick={() => removeName(name.emailPrefix)}
                          >
                            {name.firstName} {name.lastName}
                            <X className="h-3 w-3 ml-1" />
                          </Badge>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Click to remove. These names will be used across all purchased inboxes.
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {inboxNames.length === 0 && (
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    No names configured. HyperTide will generate default names if you continue.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {currentStep === 'review' && (
            <div className="space-y-6">
              <Alert>
                <Mail className="h-4 w-4" />
                <AlertDescription>
                  Review your order before starting the HyperTide automation.
                  This process typically takes 2-5 minutes per order.
                </AlertDescription>
              </Alert>

              {/* Order Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Order Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className="text-sm text-muted-foreground">Client</span>
                        <p className="font-medium">{clientName}</p>
                      </div>
                      <div>
                        <span className="text-sm text-muted-foreground">Forwarding Domain</span>
                        <p className="font-medium">{forwardingDomain}</p>
                      </div>
                    </div>

                    {orderBreakdown && (
                      <>
                        <div className="border-t pt-4">
                          <div className="grid grid-cols-3 gap-4 text-center">
                            <div>
                              <div className="text-2xl font-bold">{orderBreakdown.totalOrders}</div>
                              <div className="text-xs text-muted-foreground">Orders</div>
                            </div>
                            <div>
                              <div className="text-2xl font-bold">{orderBreakdown.totalInboxes}</div>
                              <div className="text-xs text-muted-foreground">Inboxes</div>
                            </div>
                            <div>
                              <div className="text-2xl font-bold text-green-600">
                                ${orderBreakdown.estimatedMonthlyCost}/mo
                              </div>
                              <div className="text-xs text-muted-foreground">Cost</div>
                            </div>
                          </div>
                        </div>

                        <div className="border-t pt-4">
                          <span className="text-sm text-muted-foreground">Order Details</span>
                          <div className="mt-2 space-y-2">
                            {orderBreakdown.hasEntra && (
                              <div className="flex justify-between">
                                <span>Entra ({orderBreakdown.entraOrders} order × $50)</span>
                                <span>${orderBreakdown.entraOrders * 50}/mo</span>
                              </div>
                            )}
                            {orderBreakdown.hasGoogle && (
                              <div className="flex justify-between">
                                <span>Google ({orderBreakdown.googleOrders} order × $50)</span>
                                <span>${orderBreakdown.googleOrders * 50}/mo</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </>
                    )}

                    {inboxNames.length > 0 && (
                      <div className="border-t pt-4">
                        <span className="text-sm text-muted-foreground">Inbox Names ({inboxNames.length})</span>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {inboxNames.map((name) => (
                            <Badge key={name.emailPrefix} variant="outline" className="text-xs">
                              {name.emailPrefix}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  HyperTide automation requires browser access. Ensure the server can run Playwright.
                  The purchase will use saved payment methods in Stripe.
                </AlertDescription>
              </Alert>
            </div>
          )}

          {currentStep === 'execute' && (
            <div className="space-y-6">
              {/* Progress */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    {jobStatus?.status === 'completed' ? (
                      <CheckCircle className="h-5 w-5 text-green-600" />
                    ) : jobStatus?.status === 'failed' ? (
                      <XCircle className="h-5 w-5 text-destructive" />
                    ) : (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    )}
                    {jobStatus?.status === 'completed'
                      ? 'Purchase Complete'
                      : jobStatus?.status === 'failed'
                      ? 'Purchase Failed'
                      : 'Processing Purchase'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Progress value={getProgressPercentage()} className="h-2" />

                  <div className="text-center">
                    <p className="text-sm font-medium">{jobStatus?.currentStep}</p>
                    {jobStatus && jobStatus.ordersTotal > 0 && (
                      <p className="text-xs text-muted-foreground">
                        {jobStatus.ordersCompleted} of {jobStatus.ordersTotal} orders completed
                      </p>
                    )}
                  </div>

                  {/* Results */}
                  {jobStatus?.status === 'completed' && (
                    <div className="text-center p-6 bg-green-50 rounded-lg">
                      <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-2" />
                      <p className="text-lg font-medium text-green-800">
                        Successfully created {jobStatus.totalInboxes} inboxes!
                      </p>
                    </div>
                  )}

                  {/* Errors */}
                  {jobStatus?.errors && jobStatus.errors.length > 0 && (
                    <Alert variant="destructive">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription>
                        <ul className="list-disc list-inside">
                          {jobStatus.errors.map((error, i) => (
                            <li key={i}>{error}</li>
                          ))}
                        </ul>
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </Card>

              {jobStatus?.status === 'completed' && (
                <div className="text-center">
                  <Button onClick={() => onOpenChange(false)}>
                    Close
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        {currentStep !== 'execute' && (
          <div className="flex items-center justify-between pt-4 border-t">
            <Button
              variant="outline"
              onClick={goBack}
              disabled={currentStepIndex === 0}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>

            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>

              {currentStep === 'configure' && (
                <Button onClick={goNext} disabled={!orderBreakdown}>
                  Continue
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              )}

              {currentStep === 'names' && (
                <Button onClick={goNext}>
                  Continue
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              )}

              {currentStep === 'review' && (
                <Button onClick={handleExecutePurchase} disabled={isLoading || !orderBreakdown}>
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 mr-2" />
                  )}
                  Start Purchase
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default InboxPurchaseWizard;
