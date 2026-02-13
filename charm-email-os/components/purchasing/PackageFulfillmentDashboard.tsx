'use client';

import {
  Package,
  Server,
  Mail,
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ShoppingCart,
  Sparkles,
  Globe,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import type { SubscriptionWithUsage } from '@/lib/types';

interface PackageFulfillmentDashboardProps {
  subscription: SubscriptionWithUsage | null;
  inventoryDomainsCount: number;
  purchasedNeedingSetupCount: number;
  pendingDomainsCount: number;
  approvedDomainsCount: number;
  totalInboxesCount: number;
  entraDomainsActive: number;
  googleDomainsActive: number;
  onNavigateToTab: (tab: string) => void;
}

export function PackageFulfillmentDashboard({
  subscription,
  inventoryDomainsCount,
  purchasedNeedingSetupCount,
  pendingDomainsCount,
  approvedDomainsCount,
  totalInboxesCount,
  entraDomainsActive,
  googleDomainsActive,
  onNavigateToTab,
}: PackageFulfillmentDashboardProps) {
  // No subscription state
  if (!subscription) {
    return (
      <Card className="mb-6 border-dashed">
        <CardContent className="py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-muted rounded-lg">
                <Package className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-medium">No package assigned</p>
                <p className="text-xs text-muted-foreground">
                  Assign a package on the Profile tab to see fulfillment targets
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => window.location.href = window.location.pathname.replace('/inboxes', '/profile')}>
              Go to Profile
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const entraDomainsTarget = subscription.entraDomains;
  const googleDomainsTarget = subscription.googleDomains;
  const entraDomainsNeeded = Math.max(0, entraDomainsTarget - entraDomainsActive);
  const googleDomainsNeeded = Math.max(0, googleDomainsTarget - googleDomainsActive);
  const totalDomainsNeeded = Math.max(0, subscription.totalDomains - inventoryDomainsCount);

  // Determine next action
  const getNextAction = () => {
    if (totalDomainsNeeded > 0 && pendingDomainsCount === 0 && approvedDomainsCount === 0) {
      return {
        message: `Generate ${totalDomainsNeeded} domain candidates to fill your ${subscription.packageTemplateName || 'Custom'} package`,
        action: 'procurement',
        icon: Sparkles,
        variant: 'default' as const,
      };
    }
    if (pendingDomainsCount > 0) {
      return {
        message: `${pendingDomainsCount} domains pending review — approve or deny to continue`,
        action: 'procurement',
        icon: Clock,
        variant: 'outline' as const,
      };
    }
    if (approvedDomainsCount > 0) {
      return {
        message: `${approvedDomainsCount} approved domains ready to purchase`,
        action: 'procurement',
        icon: ShoppingCart,
        variant: 'default' as const,
      };
    }
    if (purchasedNeedingSetupCount > 0) {
      return {
        message: `${purchasedNeedingSetupCount} domains purchased — set up inboxes in Hypertide`,
        action: 'procurement',
        icon: Mail,
        variant: 'default' as const,
      };
    }
    if (totalDomainsNeeded === 0 && subscription.inboxesRemaining <= 0) {
      return {
        message: `Package fully fulfilled — ${inventoryDomainsCount} domains, ${subscription.currentActiveInboxes} inboxes active`,
        action: null,
        icon: CheckCircle2,
        variant: 'outline' as const,
      };
    }
    return null;
  };

  const nextAction = getNextAction();

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        {/* Row 1: Package name + progress bars */}
        <div className="flex items-center gap-3 mb-4">
          <Badge variant="secondary" className="text-sm px-3 py-1">
            <Package className="h-3.5 w-3.5 mr-1.5" />
            {subscription.packageTemplateName || 'Custom'}
          </Badge>
          <div className="flex-1 grid grid-cols-2 gap-6">
            {/* Domains progress */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Globe className="h-3 w-3" />
                  Domains
                </span>
                <span className="font-medium">
                  {inventoryDomainsCount} / {subscription.totalDomains}
                </span>
              </div>
              <Progress value={subscription.totalDomains > 0 ? (inventoryDomainsCount / subscription.totalDomains) * 100 : 0} className="h-2" />
            </div>
            {/* Inboxes progress - use subscription data (more reliable than lazy-loaded frontend count) */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Mail className="h-3 w-3" />
                  Inboxes
                </span>
                <span className="font-medium">
                  {subscription.currentActiveInboxes} / {subscription.totalInboxes}
                </span>
              </div>
              <Progress value={subscription.totalInboxes > 0 ? (subscription.currentActiveInboxes / subscription.totalInboxes) * 100 : 0} className="h-2" />
            </div>
          </div>
        </div>

        {/* Row 2: Provider cards */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          {/* Entra */}
          <div className="flex items-center justify-between bg-blue-50 rounded-lg px-4 py-3">
            <div>
              <div className="flex items-center gap-1.5 mb-0.5">
                <div className="w-2 h-2 bg-blue-600 rounded-full" />
                <span className="text-xs font-medium text-blue-800">Microsoft Entra</span>
              </div>
              <p className="text-lg font-semibold text-blue-900">
                {entraDomainsActive} <span className="text-sm font-normal text-blue-600">/ {entraDomainsTarget} domains</span>
              </p>
            </div>
            {entraDomainsNeeded > 0 && (
              <Badge variant="outline" className="text-blue-700 border-blue-300 bg-blue-100">
                {entraDomainsNeeded} needed
              </Badge>
            )}
            {entraDomainsNeeded === 0 && (
              <CheckCircle2 className="h-5 w-5 text-blue-600" />
            )}
          </div>

          {/* Google */}
          <div className="flex items-center justify-between bg-green-50 rounded-lg px-4 py-3">
            <div>
              <div className="flex items-center gap-1.5 mb-0.5">
                <div className="w-2 h-2 bg-green-600 rounded-full" />
                <span className="text-xs font-medium text-green-800">Google Workspace</span>
              </div>
              <p className="text-lg font-semibold text-green-900">
                {googleDomainsActive} <span className="text-sm font-normal text-green-600">/ {googleDomainsTarget} domains</span>
              </p>
            </div>
            {googleDomainsNeeded > 0 && (
              <Badge variant="outline" className="text-green-700 border-green-300 bg-green-100">
                {googleDomainsNeeded} needed
              </Badge>
            )}
            {googleDomainsNeeded === 0 && (
              <CheckCircle2 className="h-5 w-5 text-green-600" />
            )}
          </div>
        </div>

        {/* Row 3: Pipeline pills */}
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <span className="text-xs text-muted-foreground mr-1">Pipeline:</span>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-yellow-50 text-yellow-700 rounded-full text-xs font-medium">
            <Clock className="h-3 w-3" />
            {pendingDomainsCount} Pending
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full text-xs font-medium">
            <CheckCircle2 className="h-3 w-3" />
            {approvedDomainsCount} Approved
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-orange-50 text-orange-700 rounded-full text-xs font-medium">
            <Server className="h-3 w-3" />
            {purchasedNeedingSetupCount} Setup
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium">
            <Globe className="h-3 w-3" />
            {inventoryDomainsCount} Active
          </div>
        </div>

        {/* Row 4: Next action banner */}
        {nextAction && (
          <div className="flex items-center justify-between bg-muted/50 rounded-lg px-4 py-2.5">
            <div className="flex items-center gap-2 text-sm">
              <nextAction.icon className="h-4 w-4 text-muted-foreground" />
              <span>{nextAction.message}</span>
            </div>
            {nextAction.action && (
              <Button
                variant={nextAction.variant}
                size="sm"
                onClick={() => onNavigateToTab(nextAction.action!)}
              >
                Go
                <ArrowRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
