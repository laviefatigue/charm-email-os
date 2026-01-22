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
      <DialogContent className="max-w-6xl w-[95vw] h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader className="flex-shrink-0 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Mail className="h-6 w-6" />
            Setup Inboxes for {clientName}
          </DialogTitle>
          <DialogDescription className="text-base">
            Configure inbox provisioning for purchased domains via HyperTide
          </DialogDescription>
        </DialogHeader>

        {/* Step Indicator - Compact horizontal */}
        <div className="flex-shrink-0 py-4 border-b bg-muted/30">
          <div className="flex items-center justify-center gap-2">
            {WIZARD_STEPS.map((step, index) => (
              <div key={step.key} className="flex items-center">
                <div
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all',
                    index < currentStepIndex
                      ? 'bg-primary text-primary-foreground'
                      : index === currentStepIndex
                      ? 'bg-primary text-primary-foreground shadow-md scale-105'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {index < currentStepIndex ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <span className="w-5 h-5 flex items-center justify-center rounded-full bg-background/20 text-xs">
                      {index + 1}
                    </span>
                  )}
                  <span className="hidden sm:inline">{step.label}</span>
                </div>
                {index < WIZARD_STEPS.length - 1 && (
                  <div
                    className={cn(
                      'w-8 h-0.5 mx-1',
                      index < currentStepIndex ? 'bg-primary' : 'bg-muted'
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Step Content - Scrollable area */}
        <div className="flex-1 overflow-y-auto py-6 px-2">
          {currentStep === 'domains' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              {/* Domain Selection */}
              <Card>
                <CardHeader className="pb-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-lg">Select Domains to Provision</CardTitle>
                      <CardDescription className="mt-1">
                        Choose which purchased domains should have inboxes created
                      </CardDescription>
                    </div>
                    <Button variant="outline" onClick={selectAllDomains}>
                      {selectedDomains.size === domains.length ? 'Deselect All' : 'Select All'}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {domains.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                      <Globe className="h-16 w-16 mx-auto mb-4 opacity-50" />
                      <p className="text-lg">No purchased domains available for setup.</p>
                      <p className="text-sm mt-2">Purchase domains first from the Domain Candidates table.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[350px] overflow-y-auto pr-2">
                      {domains.map((domain) => (
                        <div
                          key={domain.id}
                          className={cn(
                            'flex items-center justify-between p-4 rounded-lg border-2 cursor-pointer transition-all',
                            selectedDomains.has(domain.id)
                              ? 'bg-primary/10 border-primary shadow-sm'
                              : 'hover:bg-muted/50 border-transparent bg-muted/30'
                          )}
                          onClick={() => toggleDomain(domain.id)}
                        >
                          <div className="flex items-center gap-4">
                            <Checkbox
                              checked={selectedDomains.has(domain.id)}
                              onCheckedChange={() => toggleDomain(domain.id)}
                              className="h-5 w-5"
                            />
                            <div>
                              <p className="font-medium text-base">{domain.domainName}</p>
                              <p className="text-sm text-muted-foreground">
                                Status: {domain.status}
                              </p>
                            </div>
                          </div>
                          <Badge variant="secondary" className="text-sm px-3 py-1">
                            .{domain.domainName.split('.').pop()}
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
                  <CardHeader className="pb-4">
                    <CardTitle className="text-lg">Inbox Provider</CardTitle>
                    <CardDescription className="mt-1">
                      Choose the email provider for these inboxes
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <RadioGroup
                      value={providerType}
                      onValueChange={(v) => setProviderType(v as ProviderType)}
                      className="grid grid-cols-1 md:grid-cols-3 gap-4"
                    >
                      <div
                        className={cn(
                          "flex flex-col p-5 rounded-xl border-2 cursor-pointer transition-all",
                          providerType === 'entra'
                            ? "border-blue-500 bg-blue-50/50 shadow-sm"
                            : "hover:bg-muted/50 border-muted"
                        )}
                        onClick={() => setProviderType('entra')}
                      >
                        <div className="flex items-center gap-3 mb-3">
                          <RadioGroupItem value="entra" id="entra" />
                          <Label htmlFor="entra" className="text-lg font-semibold cursor-pointer">
                            Microsoft Entra
                          </Label>
                        </div>
                        <Badge className="w-fit mb-3">Recommended</Badge>
                        <p className="text-sm text-muted-foreground">
                          52 inboxes/domain<br />2 domains/order
                        </p>
                      </div>
                      <div
                        className={cn(
                          "flex flex-col p-5 rounded-xl border-2 cursor-pointer transition-all",
                          providerType === 'google'
                            ? "border-red-500 bg-red-50/50 shadow-sm"
                            : "hover:bg-muted/50 border-muted"
                        )}
                        onClick={() => setProviderType('google')}
                      >
                        <div className="flex items-center gap-3 mb-3">
                          <RadioGroupItem value="google" id="google" />
                          <Label htmlFor="google" className="text-lg font-semibold cursor-pointer">
                            Google Workspace
                          </Label>
                        </div>
                        <p className="text-sm text-muted-foreground mt-auto">
                          3 inboxes/domain<br />5 domains/order
                        </p>
                      </div>
                      <div
                        className={cn(
                          "flex flex-col p-5 rounded-xl border-2 cursor-pointer transition-all",
                          providerType === 'mixed'
                            ? "border-purple-500 bg-purple-50/50 shadow-sm"
                            : "hover:bg-muted/50 border-muted"
                        )}
                        onClick={() => setProviderType('mixed')}
                      >
                        <div className="flex items-center gap-3 mb-3">
                          <RadioGroupItem value="mixed" id="mixed" />
                          <Label htmlFor="mixed" className="text-lg font-semibold cursor-pointer">
                            Mixed
                          </Label>
                        </div>
                        <p className="text-sm text-muted-foreground mt-auto">
                          70% Entra / 30% Google<br />Balance volume & diversity
                        </p>
                      </div>
                    </RadioGroup>
                  </CardContent>
                </Card>
              )}

              {/* Order Preview */}
              {orderBreakdown && (
                <Card className="border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent">
                  <CardHeader className="pb-4">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Package className="h-5 w-5" />
                      Order Preview
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {/* Main Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center p-4 bg-background rounded-xl border shadow-sm">
                        <div className="text-3xl font-bold text-primary">{orderBreakdown.selectedDomains}</div>
                        <div className="text-sm text-muted-foreground mt-1">Domains Selected</div>
                      </div>
                      <div className="text-center p-4 bg-background rounded-xl border shadow-sm">
                        <div className="text-3xl font-bold text-primary">{orderBreakdown.totalOrders}</div>
                        <div className="text-sm text-muted-foreground mt-1">HyperTide Orders</div>
                      </div>
                      <div className="text-center p-4 bg-background rounded-xl border shadow-sm">
                        <div className="text-3xl font-bold text-primary">{orderBreakdown.totalInboxes}</div>
                        <div className="text-sm text-muted-foreground mt-1">Total Inboxes</div>
                      </div>
                      <div className="text-center p-4 bg-green-50 rounded-xl border border-green-200 shadow-sm">
                        <div className="text-3xl font-bold text-green-700">
                          ${orderBreakdown.estimatedMonthlyCost}
                        </div>
                        <div className="text-sm text-green-600 mt-1">Monthly Cost</div>
                      </div>
                    </div>

                    {orderBreakdown.extraDomainsNeeded > 0 && (
                      <Alert className="bg-amber-50 border-amber-200">
                        <AlertTriangle className="h-4 w-4 text-amber-600" />
                        <AlertDescription className="text-amber-800">
                          HyperTide orders use complete packages. {orderBreakdown.extraDomainsNeeded} additional domain(s)
                          will be purchased to fill orders.
                        </AlertDescription>
                      </Alert>
                    )}

                    {/* Provider Breakdown */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {orderBreakdown.hasEntra && (
                        <div className="p-5 rounded-xl bg-blue-50 border-2 border-blue-200">
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                              <Server className="h-5 w-5 text-blue-600" />
                              <span className="font-semibold text-blue-800 text-lg">Microsoft Entra</span>
                            </div>
                            <Badge className="bg-blue-600">{orderBreakdown.entraOrders} order(s)</Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-4 text-center">
                            <div>
                              <div className="text-2xl font-bold text-blue-700">{orderBreakdown.entraDomains}</div>
                              <div className="text-sm text-blue-600">Domains</div>
                            </div>
                            <div>
                              <div className="text-2xl font-bold text-blue-700">{orderBreakdown.entraInboxes}</div>
                              <div className="text-sm text-blue-600">Inboxes</div>
                            </div>
                          </div>
                        </div>
                      )}
                      {orderBreakdown.hasGoogle && (
                        <div className="p-5 rounded-xl bg-red-50 border-2 border-red-200">
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                              <Server className="h-5 w-5 text-red-600" />
                              <span className="font-semibold text-red-800 text-lg">Google Workspace</span>
                            </div>
                            <Badge className="bg-red-600">{orderBreakdown.googleOrders} order(s)</Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-4 text-center">
                            <div>
                              <div className="text-2xl font-bold text-red-700">{orderBreakdown.googleDomains}</div>
                              <div className="text-sm text-red-600">Domains</div>
                            </div>
                            <div>
                              <div className="text-2xl font-bold text-red-700">{orderBreakdown.googleInboxes}</div>
                              <div className="text-sm text-red-600">Inboxes</div>
                            </div>
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
            <div className="space-y-6 max-w-4xl mx-auto">
              <Card>
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Users className="h-5 w-5" />
                    Inbox Names
                  </CardTitle>
                  <CardDescription className="mt-1 text-base">
                    Configure names for inbox accounts (first.last@domain.com)
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Generate Buttons */}
                  <div className="flex gap-3 flex-wrap">
                    {onboardingData?.personas && onboardingData.personas.length > 0 && (
                      <Button onClick={loadFromPersonas} variant="default" size="lg">
                        <Users className="h-5 w-5 mr-2" />
                        Use Onboarding Personas ({onboardingData.personas.length})
                      </Button>
                    )}
                    <Button
                      onClick={handleGenerateNames}
                      disabled={isLoading}
                      variant={onboardingData?.personas?.length ? 'outline' : 'default'}
                      size="lg"
                    >
                      {isLoading ? (
                        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="h-5 w-5 mr-2" />
                      )}
                      Generate Random Names
                    </Button>
                  </div>

                  {/* Custom Name Input */}
                  <div className="p-4 rounded-xl bg-muted/50 border">
                    <Label className="text-sm font-medium mb-3 block">Add Custom Name</Label>
                    <div className="flex gap-3">
                      <Input
                        placeholder="First name"
                        value={customFirstName}
                        onChange={(e) => setCustomFirstName(e.target.value)}
                        className="text-base h-11"
                      />
                      <Input
                        placeholder="Last name"
                        value={customLastName}
                        onChange={(e) => setCustomLastName(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addCustomName()}
                        className="text-base h-11"
                      />
                      <Button variant="default" onClick={addCustomName} className="px-6 h-11">
                        Add
                      </Button>
                    </div>
                  </div>

                  {/* Names List */}
                  {inboxNames.length > 0 ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label className="text-base font-medium">Configured Names</Label>
                        <Badge variant="outline" className="text-sm">{inboxNames.length}/10</Badge>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                        {inboxNames.map((name) => (
                          <div
                            key={name.emailPrefix}
                            className="flex items-center justify-between p-3 rounded-lg bg-primary/10 border border-primary/20 cursor-pointer hover:bg-destructive/10 hover:border-destructive/30 transition-colors group"
                            onClick={() => removeName(name.emailPrefix)}
                          >
                            <span className="font-medium text-sm truncate">{name.firstName} {name.lastName}</span>
                            <X className="h-4 w-4 ml-2 opacity-50 group-hover:opacity-100 group-hover:text-destructive shrink-0" />
                          </div>
                        ))}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Click a name to remove it. These names will be used across all purchased inboxes.
                      </p>
                    </div>
                  ) : (
                    <Alert className="bg-amber-50 border-amber-200">
                      <AlertTriangle className="h-5 w-5 text-amber-600" />
                      <AlertDescription className="text-amber-800 text-base">
                        No names configured. Generate names or add them manually before proceeding.
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {currentStep === 'review' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <Alert className="bg-blue-50 border-blue-200">
                <Mail className="h-5 w-5 text-blue-600" />
                <AlertDescription className="text-blue-800 text-base">
                  Review your configuration before starting HyperTide automation.
                  This process typically takes 2-5 minutes per order.
                </AlertDescription>
              </Alert>

              {/* Order Summary */}
              <Card className="border-2">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg">Configuration Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Client Info */}
                  <div className="grid grid-cols-2 gap-6 p-4 rounded-xl bg-muted/50">
                    <div>
                      <span className="text-sm text-muted-foreground block mb-1">Client</span>
                      <p className="font-semibold text-lg">{clientName}</p>
                    </div>
                    <div>
                      <span className="text-sm text-muted-foreground block mb-1">Forwarding Domain</span>
                      <p className="font-semibold text-lg">{forwardingDomain}</p>
                    </div>
                  </div>

                  {orderBreakdown && (
                    <>
                      {/* Stats Grid */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="text-center p-4 bg-primary/5 rounded-xl border">
                          <div className="text-3xl font-bold text-primary">{orderBreakdown.selectedDomains}</div>
                          <div className="text-sm text-muted-foreground mt-1">Domains</div>
                        </div>
                        <div className="text-center p-4 bg-primary/5 rounded-xl border">
                          <div className="text-3xl font-bold text-primary">{orderBreakdown.totalOrders}</div>
                          <div className="text-sm text-muted-foreground mt-1">Orders</div>
                        </div>
                        <div className="text-center p-4 bg-primary/5 rounded-xl border">
                          <div className="text-3xl font-bold text-primary">{orderBreakdown.totalInboxes}</div>
                          <div className="text-sm text-muted-foreground mt-1">Inboxes</div>
                        </div>
                        <div className="text-center p-4 bg-green-50 rounded-xl border border-green-200">
                          <div className="text-3xl font-bold text-green-600">
                            ${orderBreakdown.estimatedMonthlyCost}
                          </div>
                          <div className="text-sm text-green-600 mt-1">Monthly</div>
                        </div>
                      </div>

                      {/* Provider Breakdown */}
                      <div>
                        <span className="text-sm font-medium text-muted-foreground block mb-3">Provider Breakdown</span>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {orderBreakdown.hasEntra && (
                            <div className="flex justify-between items-center p-4 bg-blue-50 rounded-xl border border-blue-200">
                              <div className="flex items-center gap-3">
                                <Server className="h-5 w-5 text-blue-600" />
                                <div>
                                  <span className="font-semibold text-blue-800">Entra</span>
                                  <span className="text-blue-600 text-sm ml-2">({orderBreakdown.entraOrders} order × $50)</span>
                                </div>
                              </div>
                              <span className="font-bold text-blue-700 text-lg">{orderBreakdown.entraInboxes} inboxes</span>
                            </div>
                          )}
                          {orderBreakdown.hasGoogle && (
                            <div className="flex justify-between items-center p-4 bg-red-50 rounded-xl border border-red-200">
                              <div className="flex items-center gap-3">
                                <Server className="h-5 w-5 text-red-600" />
                                <div>
                                  <span className="font-semibold text-red-800">Google</span>
                                  <span className="text-red-600 text-sm ml-2">({orderBreakdown.googleOrders} order × $50)</span>
                                </div>
                              </div>
                              <span className="font-bold text-red-700 text-lg">{orderBreakdown.googleInboxes} inboxes</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}

                  {/* Inbox Names */}
                  {inboxNames.length > 0 && (
                    <div>
                      <span className="text-sm font-medium text-muted-foreground block mb-3">
                        Inbox Names ({inboxNames.length})
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {inboxNames.map((name) => (
                          <Badge key={name.emailPrefix} variant="secondary" className="text-sm py-1 px-3">
                            {name.emailPrefix}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Selected Domains */}
                  <div>
                    <span className="text-sm font-medium text-muted-foreground block mb-3">
                      Selected Domains ({selectedDomains.size})
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {domains.filter(d => selectedDomains.has(d.id)).map((domain) => (
                        <Badge key={domain.id} variant="outline" className="text-sm py-1 px-3">
                          {domain.domainName}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Alert className="bg-amber-50 border-amber-200">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <AlertDescription className="text-amber-800 text-base">
                  HyperTide automation requires browser access. The purchase will use saved payment methods in Stripe.
                </AlertDescription>
              </Alert>
            </div>
          )}

          {currentStep === 'execute' && (
            <div className="space-y-6 max-w-3xl mx-auto">
              <Card className="border-2">
                <CardHeader className="pb-4">
                  <CardTitle className="text-xl flex items-center gap-3">
                    {jobStatus?.status === 'completed' ? (
                      <CheckCircle className="h-7 w-7 text-green-600" />
                    ) : jobStatus?.status === 'failed' ? (
                      <XCircle className="h-7 w-7 text-destructive" />
                    ) : (
                      <Loader2 className="h-7 w-7 animate-spin text-primary" />
                    )}
                    {jobStatus?.status === 'completed'
                      ? 'Provisioning Complete'
                      : jobStatus?.status === 'failed'
                      ? 'Provisioning Failed'
                      : 'Processing...'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <Progress value={getProgressPercentage()} className="h-3" />
                    <div className="flex justify-between text-sm text-muted-foreground">
                      <span>{Math.round(getProgressPercentage())}% complete</span>
                      {jobStatus && jobStatus.ordersTotal > 0 && (
                        <span>{jobStatus.ordersCompleted} of {jobStatus.ordersTotal} orders</span>
                      )}
                    </div>
                  </div>

                  <div className="text-center py-4">
                    <p className="text-lg font-medium">{jobStatus?.currentStep}</p>
                  </div>

                  {jobStatus?.status === 'completed' && (
                    <div className="text-center p-8 bg-green-50 rounded-xl border border-green-200">
                      <CheckCircle className="h-16 w-16 text-green-600 mx-auto mb-4" />
                      <p className="text-2xl font-bold text-green-800 mb-2">
                        Successfully created {jobStatus.totalInboxes} inboxes!
                      </p>
                      <p className="text-green-600">Your domains are now ready for warmup.</p>
                    </div>
                  )}

                  {jobStatus?.errors && jobStatus.errors.length > 0 && (
                    <Alert variant="destructive" className="border-2">
                      <AlertTriangle className="h-5 w-5" />
                      <AlertDescription>
                        <ul className="list-disc list-inside space-y-1">
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
                  <Button onClick={() => onOpenChange(false)} size="lg" className="px-8">
                    Close
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Navigation Footer - Fixed at bottom */}
        {currentStep !== 'execute' && (
          <div className="shrink-0 flex items-center justify-between pt-4 pb-2 px-2 border-t bg-background">
            <Button
              variant="outline"
              onClick={goBack}
              disabled={currentStepIndex === 0}
              size="lg"
              className="gap-2"
            >
              <ArrowLeft className="h-5 w-5" />
              Back
            </Button>

            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => onOpenChange(false)} size="lg">
                Cancel
              </Button>

              {currentStep === 'domains' && (
                <Button onClick={goNext} disabled={!canProceedFromDomains} size="lg" className="gap-2 px-6">
                  Continue
                  <ArrowRight className="h-5 w-5" />
                </Button>
              )}

              {currentStep === 'names' && (
                <Button onClick={goNext} disabled={!canProceedFromNames} size="lg" className="gap-2 px-6">
                  Continue
                  <ArrowRight className="h-5 w-5" />
                </Button>
              )}

              {currentStep === 'review' && (
                <Button
                  onClick={handleExecutePurchase}
                  disabled={isLoading || !orderBreakdown}
                  size="lg"
                  className="gap-2 px-6 bg-green-600 hover:bg-green-700"
                >
                  {isLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Play className="h-5 w-5" />
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
