'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
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
  AlertTriangle,
  Users,
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
  Package,
  Globe,
  Server,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { OnboardingData, OnboardingPersona } from '@/lib/types';

// Package templates based on actual infrastructure specs
const PACKAGE_TEMPLATES = {
  starter: {
    name: 'Starter Package',
    description: '37 domains, 699 inboxes',
    entraPackages: 6,   // 6 orders × 2 domains × 52 inboxes = 624
    googlePackages: 5,  // 5 orders × 5 domains × 3 inboxes = 75
    entraDomains: 12,
    entraInboxes: 624,
    googleDomains: 25,
    googleInboxes: 75,
    totalDomains: 37,
    totalInboxes: 699,
  },
  growth: {
    name: 'Growth Package',
    description: '74 domains, 1398 inboxes',
    entraPackages: 12,  // 12 orders × 2 domains × 52 inboxes = 1248
    googlePackages: 10, // 10 orders × 5 domains × 3 inboxes = 150
    entraDomains: 24,
    entraInboxes: 1248,
    googleDomains: 50,
    googleInboxes: 150,
    totalDomains: 74,
    totalInboxes: 1398,
  },
  custom: {
    name: 'Custom',
    description: 'Configure manually',
    entraPackages: 0,
    googlePackages: 0,
    entraDomains: 0,
    entraInboxes: 0,
    googleDomains: 0,
    googleInboxes: 0,
    totalDomains: 0,
    totalInboxes: 0,
  },
};

// Hypertide specs
const ENTRA_INBOXES_PER_DOMAIN = 52;
const ENTRA_DOMAINS_PER_ORDER = 2;
const GOOGLE_INBOXES_PER_DOMAIN = 3;
const GOOGLE_DOMAINS_PER_ORDER = 5;
const COST_PER_ORDER = 50;

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
  selectedDomainIds?: string[];
  onboardingData?: OnboardingData;
  onComplete?: (totalInboxes: number) => void;
}

type WizardStep = 'domains' | 'names' | 'review' | 'execute';
type PackageType = 'starter' | 'growth' | 'custom';
type ProviderType = 'entra' | 'google' | 'mixed';

const WIZARD_STEPS: { key: WizardStep; label: string; description: string }[] = [
  { key: 'domains', label: 'Domains', description: 'Select domains to provision' },
  { key: 'names', label: 'Names', description: 'Configure inbox names' },
  { key: 'review', label: 'Review', description: 'Review configuration' },
  { key: 'execute', label: 'Execute', description: 'Run provisioning' },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export function InboxPurchaseWizard({
  open,
  onOpenChange,
  clientId,
  clientName,
  forwardingDomain,
  domains,
  selectedDomainIds = [],
  onboardingData,
  onComplete,
}: InboxPurchaseWizardProps) {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('domains');
  const [isLoading, setIsLoading] = useState(false);

  // Domain selection state
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set(selectedDomainIds));
  const [providerType, setProviderType] = useState<ProviderType>('entra');

  // Names state
  const [inboxNames, setInboxNames] = useState<InboxName[]>([]);
  const [customFirstName, setCustomFirstName] = useState('');
  const [customLastName, setCustomLastName] = useState('');

  // Execution state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  // Initialize selected domains when prop changes
  useEffect(() => {
    if (selectedDomainIds.length > 0) {
      setSelectedDomains(new Set(selectedDomainIds));
    }
  }, [selectedDomainIds]);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setCurrentStep('domains');
      if (selectedDomainIds.length > 0) {
        setSelectedDomains(new Set(selectedDomainIds));
      }
    }
  }, [open, selectedDomainIds]);

  // Get current step index
  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);

  // Calculate order breakdown based on selected domains
  const orderBreakdown = useMemo(() => {
    const domainCount = selectedDomains.size;

    if (domainCount === 0) {
      return null;
    }

    let entraDomains = 0;
    let googleDomains = 0;

    if (providerType === 'entra') {
      entraDomains = domainCount;
    } else if (providerType === 'google') {
      googleDomains = domainCount;
    } else {
      // Mixed: prioritize Entra (better volume), use Google for remainder
      entraDomains = Math.min(domainCount, Math.floor(domainCount * 0.7));
      googleDomains = domainCount - entraDomains;
    }

    // Calculate orders needed (round up to complete orders)
    const entraOrders = Math.ceil(entraDomains / ENTRA_DOMAINS_PER_ORDER);
    const googleOrders = Math.ceil(googleDomains / GOOGLE_DOMAINS_PER_ORDER);

    // Actual domains used (orders × domains per order)
    const entraDomainsActual = entraOrders * ENTRA_DOMAINS_PER_ORDER;
    const googleDomainsActual = googleOrders * GOOGLE_DOMAINS_PER_ORDER;

    // Inbox counts
    const entraInboxes = entraDomainsActual * ENTRA_INBOXES_PER_DOMAIN;
    const googleInboxes = googleDomainsActual * GOOGLE_INBOXES_PER_DOMAIN;

    return {
      selectedDomains: domainCount,
      entraDomains: entraDomainsActual,
      entraOrders,
      entraInboxes,
      googleDomains: googleDomainsActual,
      googleOrders,
      googleInboxes,
      totalOrders: entraOrders + googleOrders,
      totalDomains: entraDomainsActual + googleDomainsActual,
      totalInboxes: entraInboxes + googleInboxes,
      estimatedMonthlyCost: (entraOrders + googleOrders) * COST_PER_ORDER,
      hasEntra: entraOrders > 0,
      hasGoogle: googleOrders > 0,
      extraDomainsNeeded: (entraDomainsActual + googleDomainsActual) - domainCount,
    };
  }, [selectedDomains.size, providerType]);

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

  // Toggle domain selection
  const toggleDomain = (domainId: string) => {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return next;
    });
  };

  // Select all domains
  const selectAllDomains = () => {
    if (selectedDomains.size === domains.length) {
      setSelectedDomains(new Set());
    } else {
      setSelectedDomains(new Set(domains.map(d => d.id)));
    }
  };

  // Generate inbox names
  const handleGenerateNames = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/inbox-purchasing/generate-names`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          count: 10,
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
  }, [clientId]);

  // Load names from onboarding personas
  const loadFromPersonas = useCallback(() => {
    const personas = onboardingData?.personas;
    if (!personas || personas.length === 0) {
      toast.error('No personas found in onboarding data');
      return;
    }

    const COMMON_LAST_NAMES = [
      'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
      'Davis', 'Rodriguez', 'Martinez', 'Anderson', 'Taylor', 'Thomas'
    ];

    const newNames: InboxName[] = [];

    personas.forEach((persona, index) => {
      let firstName = persona.first_name;

      if (!firstName && persona.job_title) {
        const seniorityMap: Record<string, string[]> = {
          'VP': ['Alex', 'Jordan', 'Morgan', 'Taylor', 'Cameron'],
          'Director': ['Sam', 'Jamie', 'Casey', 'Riley', 'Quinn'],
          'Manager': ['Chris', 'Pat', 'Drew', 'Blake', 'Avery'],
          'Head': ['Sydney', 'Peyton', 'Skyler', 'Reese', 'Finley'],
          'Chief': ['Alex', 'Morgan', 'Jordan', 'Sage', 'Hayden'],
          'default': ['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey']
        };

        const titleWords = persona.job_title.split(' ');
        const prefix = titleWords[0].toUpperCase();
        const namePool = seniorityMap[prefix] || seniorityMap['default'];
        firstName = namePool[index % namePool.length];
      }

      if (!firstName && persona.name) {
        const nameParts = persona.name.split(' ');
        firstName = nameParts[0];
      }

      if (!firstName) {
        const fallbackNames = ['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey'];
        firstName = fallbackNames[index % fallbackNames.length];
      }

      let lastName = persona.last_name;
      if (!lastName && persona.name) {
        const nameParts = persona.name.split(' ');
        if (nameParts.length > 1) {
          lastName = nameParts.slice(1).join(' ');
        }
      }
      if (!lastName) {
        lastName = COMMON_LAST_NAMES[index % COMMON_LAST_NAMES.length];
      }

      const emailPrefix = `${firstName.toLowerCase()}.${lastName.toLowerCase()}`;

      if (!newNames.some(n => n.emailPrefix === emailPrefix)) {
        newNames.push({ firstName, lastName, emailPrefix });
      }
    });

    const limitedNames = newNames.slice(0, 10);
    setInboxNames(limitedNames);
    toast.success(`Loaded ${limitedNames.length} names from onboarding personas`);
  }, [onboardingData]);

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
      toast.error('No domains selected');
      return;
    }

    setIsLoading(true);
    try {
      // Get selected domain details
      const selectedDomainsList = domains.filter(d => selectedDomains.has(d.id));

      const response = await fetch(`${API_BASE}/inbox-purchasing/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          client_name: clientName,
          forwarding_domain: forwardingDomain,
          inbox_target: {
            entra_inboxes: orderBreakdown.entraInboxes,
            google_inboxes: orderBreakdown.googleInboxes,
          },
          inbox_names: inboxNames.map((n) => ({
            first_name: n.firstName,
            last_name: n.lastName,
          })),
          entra_domains: selectedDomainsList
            .slice(0, orderBreakdown.entraDomains)
            .map(d => ({ domain_name: d.domainName })),
          google_domains: selectedDomainsList
            .slice(orderBreakdown.entraDomains)
            .map(d => ({ domain_name: d.domainName })),
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
  }, [clientId, clientName, forwardingDomain, inboxNames, orderBreakdown, domains, selectedDomains]);

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

  const canProceedFromDomains = selectedDomains.size > 0;
  const canProceedFromNames = inboxNames.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Setup Inboxes for {clientName}
          </DialogTitle>
          <DialogDescription>
            Configure inbox provisioning for purchased domains via HyperTide
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
          {currentStep === 'domains' && (
            <div className="space-y-6">
              {/* Domain Selection */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base">Select Domains to Provision</CardTitle>
                      <CardDescription>
                        Choose which purchased domains should have inboxes created
                      </CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={selectAllDomains}>
                      {selectedDomains.size === domains.length ? 'Deselect All' : 'Select All'}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {domains.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <Globe className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No purchased domains available for setup.</p>
                      <p className="text-sm mt-2">Purchase domains first from the Domain Candidates table.</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[200px] overflow-y-auto">
                      {domains.map((domain) => (
                        <div
                          key={domain.id}
                          className={cn(
                            'flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors',
                            selectedDomains.has(domain.id)
                              ? 'bg-primary/5 border-primary'
                              : 'hover:bg-muted/50'
                          )}
                          onClick={() => toggleDomain(domain.id)}
                        >
                          <div className="flex items-center gap-3">
                            <Checkbox
                              checked={selectedDomains.has(domain.id)}
                              onCheckedChange={() => toggleDomain(domain.id)}
                            />
                            <div>
                              <p className="font-medium">{domain.domainName}</p>
                              <p className="text-xs text-muted-foreground">
                                Status: {domain.status}
                              </p>
                            </div>
                          </div>
                          <Badge variant="outline">
                            {domain.domainName.split('.').pop()}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Provider Selection */}
              {selectedDomains.size > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Inbox Provider</CardTitle>
                    <CardDescription>
                      Choose the email provider for these inboxes
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <RadioGroup
                      value={providerType}
                      onValueChange={(v) => setProviderType(v as ProviderType)}
                      className="space-y-3"
                    >
                      <div className="flex items-center space-x-3 p-3 rounded-lg border hover:bg-muted/50">
                        <RadioGroupItem value="entra" id="entra" />
                        <Label htmlFor="entra" className="flex-1 cursor-pointer">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="font-medium">Microsoft Entra</p>
                              <p className="text-sm text-muted-foreground">
                                52 inboxes/domain, 2 domains/order
                              </p>
                            </div>
                            <Badge>Recommended</Badge>
                          </div>
                        </Label>
                      </div>
                      <div className="flex items-center space-x-3 p-3 rounded-lg border hover:bg-muted/50">
                        <RadioGroupItem value="google" id="google" />
                        <Label htmlFor="google" className="flex-1 cursor-pointer">
                          <div>
                            <p className="font-medium">Google Workspace</p>
                            <p className="text-sm text-muted-foreground">
                              3 inboxes/domain, 5 domains/order
                            </p>
                          </div>
                        </Label>
                      </div>
                      <div className="flex items-center space-x-3 p-3 rounded-lg border hover:bg-muted/50">
                        <RadioGroupItem value="mixed" id="mixed" />
                        <Label htmlFor="mixed" className="flex-1 cursor-pointer">
                          <div>
                            <p className="font-medium">Mixed (70% Entra / 30% Google)</p>
                            <p className="text-sm text-muted-foreground">
                              Balance between volume and diversity
                            </p>
                          </div>
                        </Label>
                      </div>
                    </RadioGroup>
                  </CardContent>
                </Card>
              )}

              {/* Order Preview */}
              {orderBreakdown && (
                <Card className="border-primary/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Order Preview</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.selectedDomains}</div>
                        <div className="text-xs text-muted-foreground">Domains Selected</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.totalOrders}</div>
                        <div className="text-xs text-muted-foreground">HyperTide Orders</div>
                      </div>
                      <div className="text-center p-3 bg-muted rounded-lg">
                        <div className="text-2xl font-bold">{orderBreakdown.totalInboxes}</div>
                        <div className="text-xs text-muted-foreground">Total Inboxes</div>
                      </div>
                      <div className="text-center p-3 bg-green-50 rounded-lg">
                        <div className="text-2xl font-bold text-green-700">
                          ${orderBreakdown.estimatedMonthlyCost}
                        </div>
                        <div className="text-xs text-green-600">Monthly Cost</div>
                      </div>
                    </div>

                    {orderBreakdown.extraDomainsNeeded > 0 && (
                      <Alert>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>
                          HyperTide orders use complete packages. {orderBreakdown.extraDomainsNeeded} additional domain(s)
                          will be purchased to fill orders.
                        </AlertDescription>
                      </Alert>
                    )}

                    <div className="grid grid-cols-2 gap-4 mt-4">
                      {orderBreakdown.hasEntra && (
                        <div className="p-3 border rounded-lg bg-blue-50/50">
                          <div className="font-medium flex items-center gap-2">
                            <Server className="h-4 w-4" />
                            <Badge variant="outline" className="border-blue-600 text-blue-600">Entra</Badge>
                          </div>
                          <div className="text-sm text-muted-foreground mt-2 space-y-1">
                            <p>{orderBreakdown.entraOrders} order(s)</p>
                            <p>{orderBreakdown.entraDomains} domains</p>
                            <p className="font-medium text-blue-700">{orderBreakdown.entraInboxes} inboxes</p>
                          </div>
                        </div>
                      )}
                      {orderBreakdown.hasGoogle && (
                        <div className="p-3 border rounded-lg bg-red-50/50">
                          <div className="font-medium flex items-center gap-2">
                            <Server className="h-4 w-4" />
                            <Badge variant="outline" className="border-red-600 text-red-600">Google</Badge>
                          </div>
                          <div className="text-sm text-muted-foreground mt-2 space-y-1">
                            <p>{orderBreakdown.googleOrders} order(s)</p>
                            <p>{orderBreakdown.googleDomains} domains</p>
                            <p className="font-medium text-red-700">{orderBreakdown.googleInboxes} inboxes</p>
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
                  {/* Generate Buttons */}
                  <div className="flex gap-2 flex-wrap">
                    {onboardingData?.personas && onboardingData.personas.length > 0 && (
                      <Button onClick={loadFromPersonas} variant="default">
                        <Users className="h-4 w-4 mr-2" />
                        Use Onboarding Personas ({onboardingData.personas.length})
                      </Button>
                    )}
                    <Button
                      onClick={handleGenerateNames}
                      disabled={isLoading}
                      variant={onboardingData?.personas?.length ? 'outline' : 'default'}
                    >
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4 mr-2" />
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
                      onKeyDown={(e) => e.key === 'Enter' && addCustomName()}
                    />
                    <Button variant="outline" onClick={addCustomName}>
                      Add
                    </Button>
                  </div>

                  {/* Names List */}
                  {inboxNames.length > 0 ? (
                    <div className="space-y-2">
                      <Label>Names ({inboxNames.length}/10)</Label>
                      <div className="flex flex-wrap gap-2">
                        {inboxNames.map((name) => (
                          <Badge
                            key={name.emailPrefix}
                            variant="secondary"
                            className="cursor-pointer hover:bg-destructive hover:text-destructive-foreground py-1 px-3"
                            onClick={() => removeName(name.emailPrefix)}
                          >
                            {name.firstName} {name.lastName}
                            <X className="h-3 w-3 ml-2" />
                          </Badge>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Click to remove. These names will be used across all purchased inboxes.
                      </p>
                    </div>
                  ) : (
                    <Alert>
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription>
                        No names configured. Generate names or add them manually before proceeding.
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {currentStep === 'review' && (
            <div className="space-y-6">
              <Alert className="bg-blue-50 border-blue-200">
                <Mail className="h-4 w-4" />
                <AlertDescription>
                  Review your configuration before starting HyperTide automation.
                  This process typically takes 2-5 minutes per order.
                </AlertDescription>
              </Alert>

              {/* Order Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Configuration Summary</CardTitle>
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
                          <div className="grid grid-cols-4 gap-4 text-center">
                            <div>
                              <div className="text-2xl font-bold">{orderBreakdown.selectedDomains}</div>
                              <div className="text-xs text-muted-foreground">Domains</div>
                            </div>
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
                          <span className="text-sm text-muted-foreground">Provider Breakdown</span>
                          <div className="mt-2 space-y-2">
                            {orderBreakdown.hasEntra && (
                              <div className="flex justify-between items-center p-2 bg-blue-50 rounded">
                                <span>Entra ({orderBreakdown.entraOrders} order × $50)</span>
                                <span className="font-medium">{orderBreakdown.entraInboxes} inboxes</span>
                              </div>
                            )}
                            {orderBreakdown.hasGoogle && (
                              <div className="flex justify-between items-center p-2 bg-red-50 rounded">
                                <span>Google ({orderBreakdown.googleOrders} order × $50)</span>
                                <span className="font-medium">{orderBreakdown.googleInboxes} inboxes</span>
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

                    {/* Selected Domains */}
                    <div className="border-t pt-4">
                      <span className="text-sm text-muted-foreground">Selected Domains ({selectedDomains.size})</span>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {domains.filter(d => selectedDomains.has(d.id)).map((domain) => (
                          <Badge key={domain.id} variant="secondary" className="text-xs">
                            {domain.domainName}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  HyperTide automation requires browser access. The purchase will use saved payment methods in Stripe.
                </AlertDescription>
              </Alert>
            </div>
          )}

          {currentStep === 'execute' && (
            <div className="space-y-6">
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
                      ? 'Provisioning Complete'
                      : jobStatus?.status === 'failed'
                      ? 'Provisioning Failed'
                      : 'Processing...'}
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

                  {jobStatus?.status === 'completed' && (
                    <div className="text-center p-6 bg-green-50 rounded-lg">
                      <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-2" />
                      <p className="text-lg font-medium text-green-800">
                        Successfully created {jobStatus.totalInboxes} inboxes!
                      </p>
                    </div>
                  )}

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

              {(jobStatus?.status === 'completed' || jobStatus?.status === 'failed') && (
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

              {currentStep === 'domains' && (
                <Button onClick={goNext} disabled={!canProceedFromDomains}>
                  Continue
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              )}

              {currentStep === 'names' && (
                <Button onClick={goNext} disabled={!canProceedFromNames}>
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
                  Start Provisioning
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
