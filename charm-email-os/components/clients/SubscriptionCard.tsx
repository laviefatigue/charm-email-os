'use client';

import { useState, useEffect } from 'react';
import {
  Package,
  Server,
  Mail,
  Pencil,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { SubscriptionWithUsage, PackageTemplate } from '@/lib/types';
import { subscriptionApi } from '@/lib/api';

interface SubscriptionCardProps {
  clientId: string;
  onEdit?: () => void;
}

export function SubscriptionCard({ clientId, onEdit }: SubscriptionCardProps) {
  const [subscription, setSubscription] = useState<SubscriptionWithUsage | null>(null);
  const [templates, setTemplates] = useState<PackageTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [clientId]);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [sub, temps] = await Promise.all([
        subscriptionApi.getClientSubscription(clientId),
        subscriptionApi.listTemplates(),
      ]);
      setSubscription(sub);
      setTemplates(temps);
    } catch (err) {
      console.error('Failed to load subscription:', err);
      setError('Failed to load subscription data');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplyTemplate = async (templateId: string) => {
    try {
      await subscriptionApi.applyTemplate(clientId, templateId, 'Applied from UI', 'user');
      await loadData();
    } catch (err) {
      console.error('Failed to apply template:', err);
      setError('Failed to apply package template');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Package className="h-4 w-4" />
            Package & Subscription
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            <div className="h-20 bg-gray-200 rounded"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Package className="h-4 w-4" />
            Package & Subscription
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-red-600">{error}</div>
          <Button variant="outline" size="sm" className="mt-2" onClick={loadData}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  // No subscription yet - show template selection
  if (!subscription) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Package className="h-4 w-4" />
            Package & Subscription
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            No subscription configured. Select a package to get started:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {templates.map((template) => (
              <div
                key={template.id}
                className="border rounded-lg p-4 hover:border-primary cursor-pointer transition-colors"
                onClick={() => handleApplyTemplate(template.id)}
              >
                <h4 className="font-semibold">{template.name}</h4>
                <div className="mt-2 text-sm text-muted-foreground">
                  <p>{template.totalDomains} domains</p>
                  <p>{template.totalInboxes} inboxes</p>
                  <p className="text-xs mt-1">
                    ({template.entraPackages} Entra + {template.googlePackages} Google orders)
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Subscription exists - show details
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Package className="h-4 w-4" />
          Package & Subscription
        </CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant="outline">
            {subscription.packageTemplateName || 'Custom'}
          </Badge>
          {onEdit && (
            <Button variant="outline" size="sm" onClick={onEdit}>
              <Pencil className="h-4 w-4 mr-1" />
              Edit
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* Quota Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          {/* Domains */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-blue-600" />
                <span className="text-sm font-medium">Domains</span>
              </div>
              <span className="text-sm text-muted-foreground">
                {subscription.currentActiveDomains} / {subscription.totalDomains}
              </span>
            </div>
            <Progress value={subscription.domainsUsedPercent} className="h-2" />
            <p className="text-xs text-muted-foreground">
              {subscription.domainsRemaining} remaining
            </p>
          </div>

          {/* Inboxes */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-purple-600" />
                <span className="text-sm font-medium">Inboxes</span>
              </div>
              <span className="text-sm text-muted-foreground">
                {subscription.currentActiveInboxes} / {subscription.totalInboxes}
              </span>
            </div>
            <Progress value={subscription.inboxesUsedPercent} className="h-2" />
            <p className="text-xs text-muted-foreground">
              {subscription.inboxesRemaining} remaining
            </p>
          </div>
        </div>

        {/* Provider Breakdown - Condensed */}
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
      </CardContent>
    </Card>
  );
}
