'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import {
  Building2,
  CheckCircle2,
  Pencil,
  User,
  Plus,
  Trash2,
  Server,
  Mail,
} from 'lucide-react';
import { toast } from 'sonner';
import { TabNavigation } from '@/components/layout';
import { useClientStore } from '@/lib/stores';
import { SubscriptionEditModal } from '@/components/clients/SubscriptionEditModal';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { subscriptionApi, clientApi } from '@/lib/api';
import type { SubscriptionWithUsage } from '@/lib/types';

interface SenderName {
  id: string;
  firstName: string;
  lastName: string;
  isFounder: boolean;
  prefixes: string[];
}

export default function ClientProfilePage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const { getClient, selectClient, fetchClients } = useClientStore();
  const client = getClient(clientId);

  const [showEditModal, setShowEditModal] = useState(false);
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);
  const [isLoadingSub, setIsLoadingSub] = useState(true);

  // Sender names state
  const [senderNames, setSenderNames] = useState<SenderName[]>([]);
  const [isLoadingNames, setIsLoadingNames] = useState(true);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  useEffect(() => {
    selectClient(clientId);
    fetchClients();
  }, [clientId, selectClient, fetchClients]);

  // Load subscription
  const loadSubscription = useCallback(async () => {
    setIsLoadingSub(true);
    try {
      const sub = await subscriptionApi.getClientSubscription(clientId);
      setSubscription(sub);
    } catch (err) {
      console.error('Failed to load subscription:', err);
    } finally {
      setIsLoadingSub(false);
    }
  }, [clientId]);

  // Load sender names
  const loadSenderNames = useCallback(async () => {
    setIsLoadingNames(true);
    try {
      const config = await clientApi.getSenderNameConfig(clientId);
      if (config.hasConfig && config.baseNames.length > 0) {
        const names: SenderName[] = config.baseNames.map((bn: any, idx: number) => ({
          id: `name-${idx}`,
          firstName: bn.firstName,
          lastName: bn.lastName,
          isFounder: bn.isFounder || idx === 0,
          prefixes: config.variations.map((v: any) => v.emailPrefix),
        }));
        setSenderNames(names);
      }
    } catch (err) {
      console.error('Failed to load sender names:', err);
    } finally {
      setIsLoadingNames(false);
    }
  }, [clientId]);

  useEffect(() => {
    loadSubscription();
    loadSenderNames();
  }, [loadSubscription, loadSenderNames]);

  const handleSubscriptionSaved = () => {
    loadSubscription();
  };

  const handleAddName = async () => {
    if (!firstName.trim() || !lastName.trim()) {
      toast.error('Please enter both first and last name');
      return;
    }

    setIsAdding(true);
    try {
      await clientApi.addSenderName(
        clientId,
        firstName.trim(),
        lastName.trim(),
        'entra'
      );

      // Reload sender names from API
      await loadSenderNames();
      setFirstName('');
      setLastName('');
      toast.success(`Added ${firstName.trim()} ${lastName.trim()}`);
    } catch (err) {
      console.error('Failed to add sender name:', err);
      toast.error('Failed to add sender name');
    } finally {
      setIsAdding(false);
    }
  };

  const handleDeleteName = async (index: number, name: SenderName) => {
    try {
      await clientApi.deleteSenderName(clientId, index);
      // Reload sender names from API
      await loadSenderNames();
      toast.success(`Removed ${name.firstName} ${name.lastName}`);
    } catch (err) {
      console.error('Failed to delete sender name:', err);
      toast.error('Failed to remove sender name');
    }
  };

  if (!client) {
    return (
      <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
        <div className="sticky top-0 z-50 bg-gray-50">
          <div className="max-w-[1800px] mx-auto px-4 pt-4">
            <TabNavigation clientId={clientId} />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 pt-0">
          <div className="max-w-[1800px] mx-auto">
            <div className="flex items-center justify-center h-64">
              <p className="text-muted-foreground">Client not found</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const primaryDomain = client.onboardingData?.primaryDomain || client.domain || '';
  const isLoading = isLoadingSub || isLoadingNames;

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
      {/* Sticky Header */}
      <div className="sticky top-0 z-50 bg-gray-50">
        <div className="max-w-[1800px] mx-auto px-4 pt-4">
          <TabNavigation clientId={clientId} />
        </div>
      </div>

      {/* Main Content - Scrollable */}
      <div className="flex-1 overflow-y-auto p-4 pt-0">
        <div className="max-w-[1800px] mx-auto">
          {/* Single Unified Card */}
          <Card>
        <CardContent className="p-6 space-y-0">
          {/* Client Info Section */}
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-linear-to-br from-slate-100 to-slate-200 shrink-0">
              <Building2 className="h-6 w-6 text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-semibold text-gray-900">{client.name}</h1>
              <div className="mt-2 grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 w-28">Primary Domain</span>
                  <span className="font-medium text-gray-900">
                    {primaryDomain || <span className="text-gray-400 italic">Not set</span>}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 w-28">Workspace</span>
                  {client.workspaceName ? (
                    <span className="flex items-center gap-1.5 font-medium text-gray-900">
                      {client.workspaceName}
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    </span>
                  ) : (
                    <span className="text-amber-600 italic">Not linked</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t my-6" />

          {/* Package Section */}
          {isLoadingSub ? (
            <Skeleton className="h-24 w-full" />
          ) : subscription ? (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <h2 className="text-base font-semibold">Package</h2>
                  <Badge variant="outline" className="text-sm">
                    {subscription.packageTemplateName || 'Custom'}
                  </Badge>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setShowEditModal(true)}>
                  <Pencil className="h-4 w-4 mr-1" />
                  Edit
                </Button>
              </div>

              {/* Domains & Inboxes Progress */}
              <div className="grid grid-cols-2 gap-6 mb-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Server className="h-4 w-4 text-blue-600" />
                      Domains
                    </span>
                    <span className="text-muted-foreground">
                      {subscription.currentActiveDomains} / {subscription.totalDomains}
                    </span>
                  </div>
                  <Progress value={subscription.domainsUsedPercent} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-purple-600" />
                      Inboxes
                    </span>
                    <span className="text-muted-foreground">
                      {subscription.currentActiveInboxes} / {subscription.totalInboxes}
                    </span>
                  </div>
                  <Progress value={subscription.inboxesUsedPercent} className="h-2" />
                </div>
              </div>

              {/* Provider Breakdown */}
              <div className="flex items-center gap-6 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="font-medium text-foreground">Entra:</span>
                  {subscription.entraPackages}×{subscription.entraDomainsPerPackage}={subscription.entraDomains} dom, {subscription.entraInboxes} inbx
                </span>
                <span className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="font-medium text-foreground">Google:</span>
                  {subscription.googlePackages}×{subscription.googleDomainsPerPackage}={subscription.googleDomains} dom, {subscription.googleInboxes} inbx
                </span>
              </div>
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <p>No package configured.</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => setShowEditModal(true)}>
                Configure Package
              </Button>
            </div>
          )}

          {/* Divider */}
          <div className="border-t my-6" />

          {/* Sender Names Section */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <h2 className="text-base font-semibold">Sender Names</h2>
                <Badge variant="secondary" className="text-xs">
                  {senderNames.length} {senderNames.length === 1 ? 'name' : 'names'}
                </Badge>
              </div>
            </div>

            {isLoadingNames ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <div className="space-y-3">
                {/* Existing Names */}
                {senderNames.map((name, index) => (
                  <div
                    key={name.id}
                    className="flex items-center justify-between py-3 px-4 border rounded-lg bg-muted/30"
                  >
                    <div className="flex items-center gap-3">
                      <User className="h-5 w-5 text-muted-foreground" />
                      <span className="font-medium">
                        {name.firstName} {name.lastName}
                      </span>
                      {name.isFounder && (
                        <Badge variant="outline" className="bg-indigo-50 text-indigo-700 text-xs">
                          Primary
                        </Badge>
                      )}
                      <Badge variant="secondary" className="text-xs">
                        {name.prefixes.length} prefixes
                      </Badge>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2 text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Remove Sender Name?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will remove {name.firstName} {name.lastName} and all email prefixes.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDeleteName(index, name)}
                            className="bg-destructive hover:bg-destructive/90"
                          >
                            Remove
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                ))}

                {/* Add Name Form - Always visible */}
                <div className="flex items-end gap-3 pt-2">
                  <div className="flex-1">
                    <Input
                      placeholder="First name"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddName()}
                    />
                  </div>
                  <div className="flex-1">
                    <Input
                      placeholder="Last name"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddName()}
                    />
                  </div>
                  <Button
                    onClick={handleAddName}
                    disabled={isAdding || !firstName.trim() || !lastName.trim()}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Add
                  </Button>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Edit Modal */}
      <SubscriptionEditModal
        open={showEditModal}
        onOpenChange={setShowEditModal}
        clientId={clientId}
        client={client}
        subscription={subscription}
        onSave={handleSubscriptionSaved}
      />
        </div>
      </div>
    </div>
  );
}
