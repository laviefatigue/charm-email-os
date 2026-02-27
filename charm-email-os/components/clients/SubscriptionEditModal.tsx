'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import type { SubscriptionWithUsage, PackageTemplate, Client } from '@/lib/types';
import { subscriptionApi, clientApi } from '@/lib/api';

interface SubscriptionEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  client?: Client;
  subscription: SubscriptionWithUsage | null;
  onSave?: () => void;
}

export function SubscriptionEditModal({
  open,
  onOpenChange,
  clientId,
  client,
  subscription,
  onSave,
}: SubscriptionEditModalProps) {
  const [templates, setTemplates] = useState<PackageTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [primaryDomain, setPrimaryDomain] = useState('');
  const [formData, setFormData] = useState({
    entraPackages: 6,
    googlePackages: 5,
    spareRatio: 0.15,
    notes: '',
    changeReason: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [useCustom, setUseCustom] = useState(false);

  useEffect(() => {
    if (open) {
      loadTemplates();
      // Initialize primary domain from client
      setPrimaryDomain(client?.onboardingData?.primaryDomain || '');
      if (subscription) {
        setFormData({
          entraPackages: subscription.entraPackages,
          googlePackages: subscription.googlePackages,
          spareRatio: subscription.spareRatio,
          notes: subscription.notes || '',
          changeReason: '',
        });
        setSelectedTemplateId(subscription.packageTemplateId || null);
        setUseCustom(!subscription.packageTemplateId);
      }
    }
  }, [open, subscription, client]);

  const loadTemplates = async () => {
    setIsLoading(true);
    try {
      const temps = await subscriptionApi.listTemplates();
      setTemplates(temps);
    } catch (err) {
      console.error('Failed to load templates:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTemplateSelect = (templateId: string) => {
    if (templateId === 'custom') {
      setUseCustom(true);
      setSelectedTemplateId(null);
      return;
    }

    setUseCustom(false);
    setSelectedTemplateId(templateId);
    const template = templates.find(t => t.id === templateId);
    if (template) {
      setFormData(prev => ({
        ...prev,
        entraPackages: template.entraPackages,
        googlePackages: template.googlePackages,
      }));
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      // Save primary domain if changed
      const currentPrimaryDomain = client?.onboardingData?.primaryDomain || '';
      if (primaryDomain !== currentPrimaryDomain) {
        await clientApi.update(clientId, {
          onboardingData: {
            ...client?.onboardingData,
            primaryDomain: primaryDomain || undefined,
          },
        });
      }

      if (subscription) {
        // Update existing
        await subscriptionApi.updateSubscription(clientId, {
          entraPackages: formData.entraPackages,
          googlePackages: formData.googlePackages,
          spareRatio: formData.spareRatio,
          notes: formData.notes || undefined,
          changeReason: formData.changeReason || undefined,
          changedBy: 'user',
        });
      } else if (selectedTemplateId && !useCustom) {
        // Apply template
        await subscriptionApi.applyTemplate(
          clientId,
          selectedTemplateId,
          formData.changeReason || undefined,
          'user'
        );
      } else {
        // Create custom
        await subscriptionApi.createSubscription(clientId, {
          entraPackages: formData.entraPackages,
          googlePackages: formData.googlePackages,
          spareRatio: formData.spareRatio,
          notes: formData.notes || undefined,
        });
      }

      onSave?.();
      onOpenChange(false);
    } catch (err) {
      console.error('Failed to save subscription:', err);
    } finally {
      setIsSaving(false);
    }
  };

  // Calculate preview
  const entraDomains = formData.entraPackages * 2;
  const entraInboxes = entraDomains * 52;
  const googleDomains = formData.googlePackages * 5;
  const googleInboxes = googleDomains * 3;
  const totalDomains = entraDomains + googleDomains;
  const totalInboxes = entraInboxes + googleInboxes;
  const targetSpare = Math.round(totalInboxes * formData.spareRatio);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {subscription ? 'Edit Subscription' : 'Configure Subscription'}
          </DialogTitle>
          <DialogDescription>
            Configure the package and quota settings for this client.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">Loading...</div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Primary Domain */}
            <div className="space-y-2">
              <Label htmlFor="primaryDomain">Primary Domain</Label>
              <Input
                id="primaryDomain"
                value={primaryDomain}
                onChange={(e) => setPrimaryDomain(e.target.value)}
                placeholder="e.g., hirecharm.com"
              />
              <p className="text-xs text-muted-foreground">
                The main domain associated with this client
              </p>
            </div>

            {/* Template Selection */}
            <div className="space-y-2">
              <Label>Package Template</Label>
              <Select
                value={useCustom ? 'custom' : (selectedTemplateId || '')}
                onValueChange={handleTemplateSelect}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a package" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      {template.name} ({template.totalDomains} domains, {template.totalInboxes} inboxes)
                    </SelectItem>
                  ))}
                  <SelectItem value="custom">Custom Configuration</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Custom Configuration */}
            {useCustom && (
              <div className="space-y-4 p-4 border rounded-lg bg-muted/50">
                <h4 className="font-medium">Custom Configuration</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="entraPackages">Entra Orders</Label>
                    <Input
                      id="entraPackages"
                      type="number"
                      min={0}
                      value={formData.entraPackages}
                      onChange={(e) =>
                        setFormData({ ...formData, entraPackages: parseInt(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      = {formData.entraPackages * 2} domains, {formData.entraPackages * 2 * 52} inboxes
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="googlePackages">Google Orders</Label>
                    <Input
                      id="googlePackages"
                      type="number"
                      min={0}
                      value={formData.googlePackages}
                      onChange={(e) =>
                        setFormData({ ...formData, googlePackages: parseInt(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      = {formData.googlePackages * 5} domains, {formData.googlePackages * 5 * 3} inboxes
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Spare Capacity */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Spare Capacity Target</Label>
                <span className="text-sm text-muted-foreground">
                  {Math.round(formData.spareRatio * 100)}%
                </span>
              </div>
              <Slider
                value={[formData.spareRatio * 100]}
                onValueChange={([value]) =>
                  setFormData({ ...formData, spareRatio: value / 100 })
                }
                max={50}
                step={5}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Target: {targetSpare} spare inboxes
              </p>
            </div>

            {/* Preview */}
            <div className="p-4 border rounded-lg bg-blue-50">
              <h4 className="font-medium text-blue-800 mb-2">Configuration Preview</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-blue-600">Microsoft Entra:</span>
                  <p className="font-medium">{entraDomains} domains / {entraInboxes} inboxes</p>
                </div>
                <div>
                  <span className="text-blue-600">Google Workspace:</span>
                  <p className="font-medium">{googleDomains} domains / {googleInboxes} inboxes</p>
                </div>
                <div className="col-span-2 pt-2 border-t border-blue-200">
                  <span className="text-blue-600">Total:</span>
                  <p className="font-medium text-lg">{totalDomains} domains / {totalInboxes} inboxes</p>
                </div>
              </div>
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Textarea
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Any additional notes about this subscription..."
                rows={2}
              />
            </div>

            {/* Change Reason (for updates) */}
            {subscription && (
              <div className="space-y-2">
                <Label htmlFor="changeReason">Reason for Change (optional)</Label>
                <Input
                  id="changeReason"
                  value={formData.changeReason}
                  onChange={(e) =>
                    setFormData({ ...formData, changeReason: e.target.value })
                  }
                  placeholder="e.g., Upgrading to Growth package"
                />
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving || isLoading}>
            {isSaving ? 'Saving...' : subscription ? 'Update Subscription' : 'Create Subscription'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
