'use client';

import { useState, useEffect } from 'react';
import {
  Package,
  Server,
  Mail,
  Pencil,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
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
  const spareStatusColor = {
    healthy: 'text-green-600 bg-green-50',
    low: 'text-yellow-600 bg-yellow-50',
    critical: 'text-red-600 bg-red-50',
  }[subscription.spareStatus];

  const SpareIcon = subscription.spareStatus === 'healthy' ? CheckCircle2 : AlertTriangle;

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

        {/* Provider Breakdown */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-blue-50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
              <span className="text-sm font-medium text-blue-800">Microsoft Entra</span>
            </div>
            <p className="text-xs text-blue-600">
              {subscription.entraPackages} orders × {subscription.entraDomainsPerPackage} domains
            </p>
            <p className="text-lg font-semibold text-blue-800">
              {subscription.entraDomains} domains / {subscription.entraInboxes} inboxes
            </p>
          </div>

          <div className="bg-green-50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2 h-2 bg-green-600 rounded-full"></div>
              <span className="text-sm font-medium text-green-800">Google Workspace</span>
            </div>
            <p className="text-xs text-green-600">
              {subscription.googlePackages} orders × {subscription.googleDomainsPerPackage} domains
            </p>
            <p className="text-lg font-semibold text-green-800">
              {subscription.googleDomains} domains / {subscription.googleInboxes} inboxes
            </p>
          </div>
        </div>

        {/* Inventory Status */}
        <div className="border-t pt-4">
          <h4 className="text-sm font-medium mb-3">Current Inventory</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {subscription.currentActiveInboxes}
              </div>
              <div className="text-xs text-muted-foreground">Active</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">
                {subscription.currentWarmingInboxes}
              </div>
              <div className="text-xs text-muted-foreground">Warming</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {subscription.currentSpareInboxes}
              </div>
              <div className="text-xs text-muted-foreground">Spare</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">
                {subscription.currentFlaggedInboxes}
              </div>
              <div className="text-xs text-muted-foreground">Flagged</div>
            </div>
          </div>
        </div>

        {/* Spare Capacity Status */}
        <div className="mt-4 flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${spareStatusColor}`}>
            <SpareIcon className="h-3 w-3" />
            <span className="capitalize">Spare: {subscription.spareStatus}</span>
          </div>
          <span className="text-xs text-muted-foreground">
            ({subscription.currentSpareInboxes} / {subscription.targetSpareInboxes} target)
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
