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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
  AlertTriangle,
  Users,
  Play,
  CheckCircle,
  XCircle,
  Globe,
  Server,
  Plus,
  Trash2,
  Crown,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { Domain, SenderNameForProvisioning, InfrastructureType, SubscriptionWithUsage } from '@/lib/types';
import { HYPERTIDE_CONSTRAINTS } from '@/lib/types';
import { inboxProvisioningApi } from '@/lib/api';

// Types
interface OrderGroupUI {
  id: string;
  orderType: InfrastructureType;
  domainIds: string[];
  senderNameId: string;
}

interface JobStatus {
  jobId: string;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  currentStep?: string;
  ordersCompleted: number;
  ordersTotal: number;
  totalInboxes: number;
  errors: string[];
}

interface InboxPurchaseWizardV2Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  forwardingDomain: string;
  domains: Domain[];
  selectedDomainIds?: string[];
  subscription?: SubscriptionWithUsage | null;
  onComplete?: (totalInboxes: number) => void;
}

type WizardStep = 'grouping' | 'names' | 'review' | 'execute';

const WIZARD_STEPS: { key: WizardStep; label: string; description: string }[] = [
  { key: 'grouping', label: 'Group Domains', description: 'Assign domains to Entra or Google orders' },
  { key: 'names', label: 'Select Names', description: 'Choose sender names for each order' },
  { key: 'review', label: 'Review', description: 'Confirm order configuration' },
  { key: 'execute', label: 'Execute', description: 'Run provisioning' },
];

export function InboxPurchaseWizardV2({
  open,
  onOpenChange,
  clientId,
  clientName,
  forwardingDomain,
  domains,
  selectedDomainIds = [],
  subscription,
  onComplete,
}: InboxPurchaseWizardV2Props) {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('grouping');
  const [isLoading, setIsLoading] = useState(false);

  // Sender names state
  const [senderNames, setSenderNames] = useState<SenderNameForProvisioning[]>([]);
  const [loadingSenderNames, setLoadingSenderNames] = useState(false);

  // Order groups state
  const [orderGroups, setOrderGroups] = useState<OrderGroupUI[]>([]);
  const [unassignedDomains, setUnassignedDomains] = useState<string[]>([]);

  // Age override state
  const [overrideAgeCheck, setOverrideAgeCheck] = useState(false);

  // Execution state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  // Initialize when dialog opens
  useEffect(() => {
    if (open) {
      setCurrentStep('grouping');
      setOrderGroups([]);
      setUnassignedDomains(selectedDomainIds.length > 0 ? selectedDomainIds : domains.map(d => d.id));
      setJobId(null);
      setJobStatus(null);
      loadSenderNames();
    }
  }, [open, selectedDomainIds, domains]);

  // Load sender names from API
  const loadSenderNames = async () => {
    setLoadingSenderNames(true);
    try {
      const response = await inboxProvisioningApi.getSenderNamesForProvisioning(clientId);
      setSenderNames(response.senderNames);
    } catch (error) {
      console.error('Failed to load sender names:', error);
      toast.error('Failed to load sender names');
    } finally {
      setLoadingSenderNames(false);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  // Get current step index
  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);

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

  // Add a new order group
  const addOrderGroup = (orderType: InfrastructureType) => {
    const requiredDomains = HYPERTIDE_CONSTRAINTS[orderType].domainsPerOrder;
    const availableDomains = unassignedDomains.slice(0, requiredDomains);

    if (availableDomains.length < requiredDomains) {
      toast.error(`Need ${requiredDomains} domains for ${orderType} order, but only ${availableDomains.length} available`);
      return;
    }

    const newGroup: OrderGroupUI = {
      id: `group-${Date.now()}`,
      orderType,
      domainIds: availableDomains,
      senderNameId: senderNames[0]?.id || '',
    };

    setOrderGroups(prev => [...prev, newGroup]);
    setUnassignedDomains(prev => prev.filter(id => !availableDomains.includes(id)));
  };

  // Remove an order group
  const removeOrderGroup = (groupId: string) => {
    const group = orderGroups.find(g => g.id === groupId);
    if (group) {
      setUnassignedDomains(prev => [...prev, ...group.domainIds]);
      setOrderGroups(prev => prev.filter(g => g.id !== groupId));
    }
  };

  // Update sender name for a group
  const updateGroupSenderName = (groupId: string, senderNameId: string) => {
    setOrderGroups(prev =>
      prev.map(g => (g.id === groupId ? { ...g, senderNameId } : g))
    );
  };

  // Move domain between groups
  const moveDomainToGroup = (domainId: string, targetGroupId: string | null) => {
    // Remove from current location
    let sourceDomain: string | null = null;

    // Check if domain is in a group
    const sourceGroup = orderGroups.find(g => g.domainIds.includes(domainId));
    if (sourceGroup) {
      // Can't remove if it would make the group incomplete
      const requiredCount = HYPERTIDE_CONSTRAINTS[sourceGroup.orderType].domainsPerOrder;
      if (sourceGroup.domainIds.length <= requiredCount) {
        toast.error(`Cannot remove domain - ${sourceGroup.orderType} orders require exactly ${requiredCount} domains`);
        return;
      }
      sourceDomain = domainId;
      setOrderGroups(prev =>
        prev.map(g =>
          g.id === sourceGroup.id
            ? { ...g, domainIds: g.domainIds.filter(id => id !== domainId) }
            : g
        )
      );
    } else if (unassignedDomains.includes(domainId)) {
      sourceDomain = domainId;
      setUnassignedDomains(prev => prev.filter(id => id !== domainId));
    }

    if (!sourceDomain) return;

    // Add to target
    if (targetGroupId === null) {
      setUnassignedDomains(prev => [...prev, sourceDomain!]);
    } else {
      const targetGroup = orderGroups.find(g => g.id === targetGroupId);
      if (targetGroup) {
        const requiredCount = HYPERTIDE_CONSTRAINTS[targetGroup.orderType].domainsPerOrder;
        if (targetGroup.domainIds.length >= requiredCount) {
          toast.error(`${targetGroup.orderType} order already has ${requiredCount} domains`);
          setUnassignedDomains(prev => [...prev, sourceDomain!]);
          return;
        }
        setOrderGroups(prev =>
          prev.map(g =>
            g.id === targetGroupId
              ? { ...g, domainIds: [...g.domainIds, sourceDomain!] }
              : g
          )
        );
      }
    }
  };

  // Calculate order summary
  const orderSummary = useMemo(() => {
    const entraGroups = orderGroups.filter(g => g.orderType === 'entra');
    const googleGroups = orderGroups.filter(g => g.orderType === 'google');

    const entraOrders = entraGroups.length;
    const googleOrders = googleGroups.length;
    const totalOrders = entraOrders + googleOrders;

    const entraInboxes = entraOrders * HYPERTIDE_CONSTRAINTS.entra.inboxesPerOrder;
    const googleInboxes = googleOrders * HYPERTIDE_CONSTRAINTS.google.inboxesPerOrder;
    const totalInboxes = entraInboxes + googleInboxes;

    const totalDomains = orderGroups.reduce((sum, g) => sum + g.domainIds.length, 0);
    const estimatedMonthlyCost = totalOrders * 50;

    // Check if all groups are complete
    const allGroupsComplete = orderGroups.every(g => {
      const required = HYPERTIDE_CONSTRAINTS[g.orderType].domainsPerOrder;
      return g.domainIds.length === required;
    });

    // Check if all groups have sender names
    const allGroupsHaveNames = orderGroups.every(g => g.senderNameId);

    return {
      entraOrders,
      googleOrders,
      totalOrders,
      entraInboxes,
      googleInboxes,
      totalInboxes,
      totalDomains,
      estimatedMonthlyCost,
      allGroupsComplete,
      allGroupsHaveNames,
      canProceed: totalOrders > 0 && allGroupsComplete && allGroupsHaveNames,
    };
  }, [orderGroups]);

  // Get domain by ID
  const getDomainById = (id: string) => domains.find(d => d.id === id);

  // Execute purchase
  const handleExecutePurchase = useCallback(async () => {
    if (!orderSummary.canProceed) {
      toast.error('Please complete all order groups before proceeding');
      return;
    }

    setIsLoading(true);
    try {
      const response = await inboxProvisioningApi.executePurchase({
        clientId,
        clientName,
        forwardingDomain,
        orderGroups: orderGroups.map(g => ({
          orderType: g.orderType,
          domainIds: g.domainIds,
          domainNames: g.domainIds.map(id => getDomainById(id)?.domainName || getDomainById(id)?.domain || ''),
          senderNameId: g.senderNameId,
        })),
        overrideAgeCheck,
        useSavedPayment: true,
      });

      setJobId(response.jobId);
      setJobStatus({
        jobId: response.jobId,
        status: 'pending',
        currentStep: 'Initializing...',
        ordersCompleted: 0,
        ordersTotal: orderSummary.totalOrders,
        totalInboxes: 0,
        errors: [],
      });

      // Start polling for status
      const interval = setInterval(() => pollJobStatus(response.jobId), 3000);
      setPollingInterval(interval);

      toast.success('Purchase job started');
      goNext();
    } catch (error: any) {
      const errorMessage = error?.message || 'Failed to start purchase';
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [clientId, clientName, forwardingDomain, orderGroups, orderSummary, overrideAgeCheck]);

  // Poll job status
  const pollJobStatus = async (id: string) => {
    try {
      const data = await inboxProvisioningApi.getJobStatus(id);
      setJobStatus({
        jobId: data.jobId,
        status: data.status as JobStatus['status'],
        currentStep: data.currentStep,
        ordersCompleted: data.ordersCompleted,
        ordersTotal: data.ordersTotal,
        totalInboxes: data.totalInboxes,
        errors: data.errors || [],
      });

      if (data.status === 'completed' || data.status === 'failed') {
        if (pollingInterval) {
          clearInterval(pollingInterval);
          setPollingInterval(null);
        }

        if (data.status === 'completed') {
          toast.success(`Successfully created ${data.totalInboxes} inboxes!`);
          onComplete?.(data.totalInboxes);
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
      case 'executing':
        return 20 + (jobStatus.ordersCompleted / Math.max(jobStatus.ordersTotal, 1)) * 70;
      case 'completed':
        return 100;
      case 'failed':
        return 100;
      default:
        return 0;
    }
  };

  const canProceedFromGrouping = orderSummary.totalOrders > 0 && orderSummary.allGroupsComplete;
  const canProceedFromNames = orderSummary.allGroupsHaveNames;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-[95vw] !w-[95vw] h-[90vh] flex flex-col overflow-hidden" style={{ maxWidth: '95vw', width: '95vw' }}>
        <DialogHeader className="flex-shrink-0 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Mail className="h-6 w-6" />
            Setup Inboxes for {clientName}
          </DialogTitle>
          <DialogDescription className="text-base">
            Configure inbox provisioning with domain grouping for HyperTide
          </DialogDescription>
        </DialogHeader>

        {/* Step Indicator */}
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

        {/* Step Content */}
        <div className="flex-1 overflow-y-auto py-6 px-2">
          {/* Step 1: Domain Grouping */}
          {currentStep === 'grouping' && (
            <div className="space-y-6 max-w-6xl mx-auto">
              {/* Hypertide Requirements Info */}
              <Alert className="bg-blue-50 border-blue-200">
                <Server className="h-5 w-5 text-blue-600" />
                <AlertDescription className="text-blue-800">
                  <strong>Hypertide Order Requirements:</strong> Entra orders need exactly 2 domains (100 inboxes/order).
                  Google orders need exactly 5 domains (15 inboxes/order).
                </AlertDescription>
              </Alert>

              {/* Add Order Buttons */}
              <Card>
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg">Create Order Groups</CardTitle>
                  <CardDescription>
                    Group your domains into Hypertide orders. Each order type has fixed domain requirements.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-4">
                    <Button
                      variant="outline"
                      onClick={() => addOrderGroup('entra')}
                      disabled={unassignedDomains.length < 2}
                      className="border-blue-300 hover:bg-blue-50"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Add Entra Order (2 domains → 100 inboxes)
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => addOrderGroup('google')}
                      disabled={unassignedDomains.length < 5}
                      className="border-red-300 hover:bg-red-50"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Add Google Order (5 domains → 15 inboxes)
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Order Groups */}
              {orderGroups.length > 0 && (
                <div className="space-y-4">
                  {orderGroups.map((group, index) => {
                    const constraint = HYPERTIDE_CONSTRAINTS[group.orderType];
                    const isComplete = group.domainIds.length === constraint.domainsPerOrder;

                    return (
                      <Card
                        key={group.id}
                        className={cn(
                          'border-2',
                          group.orderType === 'entra' ? 'border-blue-300 bg-blue-50/30' : 'border-red-300 bg-red-50/30'
                        )}
                      >
                        <CardHeader className="pb-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <Server className={cn('h-5 w-5', group.orderType === 'entra' ? 'text-blue-600' : 'text-red-600')} />
                              <CardTitle className="text-lg">
                                {group.orderType === 'entra' ? 'Entra' : 'Google'} Order #{index + 1}
                              </CardTitle>
                              <Badge variant={isComplete ? 'default' : 'outline'} className={cn(
                                isComplete
                                  ? group.orderType === 'entra' ? 'bg-blue-600' : 'bg-red-600'
                                  : 'border-amber-500 text-amber-600'
                              )}>
                                {group.domainIds.length}/{constraint.domainsPerOrder} domains
                                {!isComplete && ` (need ${constraint.domainsPerOrder - group.domainIds.length} more)`}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="secondary">
                                {constraint.inboxesPerOrder} inboxes
                              </Badge>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => removeOrderGroup(group.id)}
                                className="text-destructive hover:text-destructive"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="flex flex-wrap gap-2">
                            {group.domainIds.map(domainId => {
                              const domain = getDomainById(domainId);
                              return (
                                <Badge key={domainId} variant="secondary" className="text-sm py-1 px-3">
                                  <Globe className="h-3 w-3 mr-1" />
                                  {domain?.domainName || domain?.domain || domainId}
                                </Badge>
                              );
                            })}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* Unassigned Domains */}
              {unassignedDomains.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Globe className="h-5 w-5 text-muted-foreground" />
                      Unassigned Domains ({unassignedDomains.length})
                    </CardTitle>
                    <CardDescription>
                      These domains are not yet assigned to an order group
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {unassignedDomains.map(domainId => {
                        const domain = getDomainById(domainId);
                        return (
                          <Badge key={domainId} variant="outline" className="text-sm py-1 px-3">
                            {domain?.domainName || domain?.domain || domainId}
                          </Badge>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Order Summary */}
              {orderSummary.totalOrders > 0 && (
                <Card className="border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Order Summary</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                      <div className="text-center p-3 bg-background rounded-lg border">
                        <div className="text-2xl font-bold text-primary">{orderSummary.totalOrders}</div>
                        <div className="text-sm text-muted-foreground">Orders</div>
                      </div>
                      <div className="text-center p-3 bg-background rounded-lg border">
                        <div className="text-2xl font-bold text-primary">{orderSummary.totalDomains}</div>
                        <div className="text-sm text-muted-foreground">Domains</div>
                      </div>
                      <div className="text-center p-3 bg-background rounded-lg border">
                        <div className="text-2xl font-bold text-primary">{orderSummary.totalInboxes}</div>
                        <div className="text-sm text-muted-foreground">Inboxes</div>
                      </div>
                      <div className="text-center p-3 bg-blue-50 rounded-lg border border-blue-200">
                        <div className="text-2xl font-bold text-blue-700">{orderSummary.entraInboxes}</div>
                        <div className="text-sm text-blue-600">Entra</div>
                      </div>
                      <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
                        <div className="text-2xl font-bold text-green-700">${orderSummary.estimatedMonthlyCost}/mo</div>
                        <div className="text-sm text-green-600">Cost</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {orderGroups.length === 0 && (
                <div className="text-center py-12 text-muted-foreground">
                  <Server className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">No order groups created yet.</p>
                  <p className="text-sm mt-2">Create Entra or Google orders to assign domains.</p>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Sender Name Selection */}
          {currentStep === 'names' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              {loadingSenderNames ? (
                <div className="text-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                  <p>Loading sender names...</p>
                </div>
              ) : senderNames.length === 0 ? (
                <Alert variant="destructive">
                  <AlertTriangle className="h-5 w-5" />
                  <AlertDescription>
                    No sender names configured for this client. Please go to the Names tab and set up sender names first.
                  </AlertDescription>
                </Alert>
              ) : (
                <>
                  <Alert className="bg-blue-50 border-blue-200">
                    <Users className="h-5 w-5 text-blue-600" />
                    <AlertDescription className="text-blue-800">
                      Select which sender name to use for each order group. The prefixes from each name will be converted to inboxes.
                    </AlertDescription>
                  </Alert>

                  {/* Available Sender Names */}
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg">Available Sender Names</CardTitle>
                      <CardDescription>
                        These names have been configured with email prefix variations
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {senderNames.map(name => (
                          <div
                            key={name.id}
                            className="p-4 rounded-lg border bg-muted/30"
                          >
                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-4 w-4 text-muted-foreground" />
                              <span className="font-medium">{name.firstName} {name.lastName}</span>
                              {name.isFounder && (
                                <Badge variant="default" className="text-xs bg-amber-500">
                                  <Crown className="h-3 w-3 mr-1" />
                                  Founder
                                </Badge>
                              )}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {name.totalPrefixCount} prefixes • Entra: {name.entraPrefixCount} usable • Google: {name.googlePrefixCount} usable
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Order Groups with Name Selection */}
                  <div className="space-y-4">
                    {orderGroups.map((group, index) => {
                      const constraint = HYPERTIDE_CONSTRAINTS[group.orderType];
                      const selectedName = senderNames.find(n => n.id === group.senderNameId);

                      return (
                        <Card
                          key={group.id}
                          className={cn(
                            'border-2',
                            group.orderType === 'entra' ? 'border-blue-300' : 'border-red-300'
                          )}
                        >
                          <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                              <CardTitle className="text-lg flex items-center gap-2">
                                <Server className={cn('h-5 w-5', group.orderType === 'entra' ? 'text-blue-600' : 'text-red-600')} />
                                {group.orderType === 'entra' ? 'Entra' : 'Google'} Order #{index + 1}
                              </CardTitle>
                              <Badge variant="secondary">
                                {constraint.inboxesPerOrder} inboxes
                              </Badge>
                            </div>
                            <CardDescription>
                              Domains: {group.domainIds.map(id => getDomainById(id)?.domainName || getDomainById(id)?.domain).join(', ')}
                            </CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="space-y-3">
                              <Label className="text-sm font-medium">Select Sender Name</Label>
                              <Select
                                value={group.senderNameId}
                                onValueChange={(value) => updateGroupSenderName(group.id, value)}
                              >
                                <SelectTrigger>
                                  <SelectValue placeholder="Select a sender name" />
                                </SelectTrigger>
                                <SelectContent>
                                  {senderNames.map(name => (
                                    <SelectItem key={name.id} value={name.id}>
                                      {name.firstName} {name.lastName}
                                      {name.isFounder && ' (Founder)'}
                                      {' - '}
                                      {group.orderType === 'entra' ? name.entraPrefixCount : name.googlePrefixCount} prefixes
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>

                              {selectedName && (
                                <div className="text-sm text-muted-foreground p-3 rounded-lg bg-muted/50">
                                  <strong>Prefixes to be used:</strong>{' '}
                                  {(group.orderType === 'entra' ? selectedName.entraPrefixes : selectedName.googlePrefixes)
                                    .slice(0, 5)
                                    .join(', ')}
                                  {(group.orderType === 'entra' ? selectedName.entraPrefixCount : selectedName.googlePrefixCount) > 5 && '...'}
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Step 3: Review */}
          {currentStep === 'review' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <Alert className="bg-blue-50 border-blue-200">
                <Mail className="h-5 w-5 text-blue-600" />
                <AlertDescription className="text-blue-800 text-base">
                  Review your configuration before starting HyperTide automation.
                  This process typically takes 2-5 minutes per order.
                </AlertDescription>
              </Alert>

              {/* Summary Card */}
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

                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="text-center p-4 bg-primary/5 rounded-xl border">
                      <div className="text-3xl font-bold text-primary">{orderSummary.totalOrders}</div>
                      <div className="text-sm text-muted-foreground mt-1">Orders</div>
                    </div>
                    <div className="text-center p-4 bg-primary/5 rounded-xl border">
                      <div className="text-3xl font-bold text-primary">{orderSummary.totalDomains}</div>
                      <div className="text-sm text-muted-foreground mt-1">Domains</div>
                    </div>
                    <div className="text-center p-4 bg-primary/5 rounded-xl border">
                      <div className="text-3xl font-bold text-primary">{orderSummary.totalInboxes}</div>
                      <div className="text-sm text-muted-foreground mt-1">Inboxes</div>
                    </div>
                    <div className="text-center p-4 bg-green-50 rounded-xl border border-green-200">
                      <div className="text-3xl font-bold text-green-600">
                        ${orderSummary.estimatedMonthlyCost}
                      </div>
                      <div className="text-sm text-green-600 mt-1">Monthly</div>
                    </div>
                  </div>

                  {/* Order Details */}
                  <div className="space-y-3">
                    <span className="text-sm font-medium text-muted-foreground">Order Breakdown</span>
                    {orderGroups.map((group, index) => {
                      const selectedName = senderNames.find(n => n.id === group.senderNameId);
                      const constraint = HYPERTIDE_CONSTRAINTS[group.orderType];

                      return (
                        <div
                          key={group.id}
                          className={cn(
                            'p-4 rounded-lg border-2',
                            group.orderType === 'entra' ? 'bg-blue-50 border-blue-200' : 'bg-red-50 border-red-200'
                          )}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <Server className={cn('h-4 w-4', group.orderType === 'entra' ? 'text-blue-600' : 'text-red-600')} />
                              <span className={cn('font-semibold', group.orderType === 'entra' ? 'text-blue-800' : 'text-red-800')}>
                                {group.orderType === 'entra' ? 'Entra' : 'Google'} Order #{index + 1}
                              </span>
                            </div>
                            <Badge className={group.orderType === 'entra' ? 'bg-blue-600' : 'bg-red-600'}>
                              {constraint.inboxesPerOrder} inboxes
                            </Badge>
                          </div>
                          <div className="text-sm space-y-1">
                            <p><strong>Domains:</strong> {group.domainIds.map(id => getDomainById(id)?.domainName || getDomainById(id)?.domain).join(', ')}</p>
                            <p><strong>Sender Name:</strong> {selectedName ? `${selectedName.firstName} ${selectedName.lastName}` : 'Not selected'}</p>
                          </div>
                        </div>
                      );
                    })}
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

          {/* Step 4: Execute */}
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

        {/* Navigation Footer */}
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

              {currentStep === 'grouping' && (
                <Button onClick={goNext} disabled={!canProceedFromGrouping} size="lg" className="gap-2 px-6">
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
                  disabled={isLoading || !orderSummary.canProceed}
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

function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <label className={cn('text-sm font-medium leading-none', className)}>{children}</label>;
}

export default InboxPurchaseWizardV2;
