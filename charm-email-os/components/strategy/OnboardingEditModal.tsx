'use client';

import { useState } from 'react';
import {
  Building2,
  Package,
  Target,
  Users,
  Briefcase,
  MessageSquare,
  Trophy,
  X,
  Save,
  Loader2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { onboardingApi, type OnboardingSubmission } from '@/lib/api';

interface OnboardingEditModalProps {
  submission: OnboardingSubmission;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (updated: OnboardingSubmission) => void;
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 border-b pb-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <h3 className="font-medium text-sm">{title}</h3>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        {label}
      </Label>
      {children}
    </div>
  );
}

function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}) {
  const [inputValue, setInputValue] = useState('');

  const addTag = () => {
    if (inputValue.trim() && !value.includes(inputValue.trim())) {
      onChange([...value, inputValue.trim()]);
      setInputValue('');
    }
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTag();
            }
          }}
          className="flex-1"
        />
        <Button type="button" variant="outline" size="sm" onClick={addTag}>
          Add
        </Button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((tag) => (
            <Badge
              key={tag}
              variant="secondary"
              className="text-xs cursor-pointer hover:bg-destructive hover:text-destructive-foreground"
              onClick={() => removeTag(tag)}
            >
              {tag} <X className="h-3 w-3 ml-1" />
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export function OnboardingEditModal({
  submission,
  open,
  onOpenChange,
  onSave,
}: OnboardingEditModalProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    // Foundation
    companyName: submission.companyName || '',
    website: submission.website || '',
    contactName: submission.contactName || '',
    contactEmail: submission.contactEmail || '',
    employeeCount: submission.employeeCount || '',
    fundingStage: submission.fundingStage || '',
    hqLocation: submission.hqLocation || '',

    // Offering
    coreProduct: submission.coreProduct || '',
    targetCustomer: submission.targetCustomer || '',
    acv: submission.acv || '',
    salesCycleLength: submission.salesCycleLength || '',

    // Market Signals
    signals: submission.signals || [],

    // Audience
    jobTitles: submission.jobTitles || [],

    // Process
    outboundTools: submission.outboundTools || [],
    crm: submission.crm || '',

    // Messaging
    customerVoice: submission.customerVoice || '',
    roiResults: submission.roiResults || '',
    toneStyle: submission.toneStyle || '',

    // Goals
    primaryGtmObjective: submission.primaryGtmObjective || '',
    successMetrics: submission.successMetrics || [],
    successDefinition: submission.successDefinition || '',
  });

  const updateField = (field: string, value: string | string[]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      // Convert camelCase to snake_case for API
      const updatePayload = {
        company_name: formData.companyName || undefined,
        website: formData.website || undefined,
        contact_name: formData.contactName || undefined,
        contact_email: formData.contactEmail || undefined,
        employee_count: formData.employeeCount || undefined,
        funding_stage: formData.fundingStage || undefined,
        hq_location: formData.hqLocation || undefined,
        core_product: formData.coreProduct || undefined,
        target_customer: formData.targetCustomer || undefined,
        acv: formData.acv || undefined,
        sales_cycle_length: formData.salesCycleLength || undefined,
        signals: formData.signals.length > 0 ? formData.signals : undefined,
        job_titles: formData.jobTitles.length > 0 ? formData.jobTitles : undefined,
        outbound_tools: formData.outboundTools.length > 0 ? formData.outboundTools : undefined,
        crm: formData.crm || undefined,
        customer_voice: formData.customerVoice || undefined,
        roi_results: formData.roiResults || undefined,
        tone_style: formData.toneStyle || undefined,
        primary_gtm_objective: formData.primaryGtmObjective || undefined,
        success_metrics: formData.successMetrics.length > 0 ? formData.successMetrics : undefined,
        success_definition: formData.successDefinition || undefined,
      };

      const updated = await onboardingApi.updateSubmission(submission.id, updatePayload);
      onSave(updated);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            Edit Onboarding Profile
          </DialogTitle>
        </DialogHeader>

        {error && (
          <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md">
            {error}
          </div>
        )}

        <div className="space-y-6 py-4">
          {/* Section 1: Foundation */}
          <Section icon={Building2} title="Foundation">
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Company Name">
                <Input
                  value={formData.companyName}
                  onChange={(e) => updateField('companyName', e.target.value)}
                />
              </FormField>
              <FormField label="Website">
                <Input
                  value={formData.website}
                  onChange={(e) => updateField('website', e.target.value)}
                  placeholder="https://example.com"
                />
              </FormField>
              <FormField label="Contact Name">
                <Input
                  value={formData.contactName}
                  onChange={(e) => updateField('contactName', e.target.value)}
                />
              </FormField>
              <FormField label="Contact Email">
                <Input
                  type="email"
                  value={formData.contactEmail}
                  onChange={(e) => updateField('contactEmail', e.target.value)}
                />
              </FormField>
              <FormField label="Employee Count">
                <Input
                  value={formData.employeeCount}
                  onChange={(e) => updateField('employeeCount', e.target.value)}
                  placeholder="e.g., 10-50"
                />
              </FormField>
              <FormField label="Funding Stage">
                <Input
                  value={formData.fundingStage}
                  onChange={(e) => updateField('fundingStage', e.target.value)}
                  placeholder="e.g., Series A"
                />
              </FormField>
              <FormField label="HQ Location">
                <Input
                  value={formData.hqLocation}
                  onChange={(e) => updateField('hqLocation', e.target.value)}
                  placeholder="e.g., San Francisco, CA"
                />
              </FormField>
            </div>
          </Section>

          {/* Section 2: Offering */}
          <Section icon={Package} title="Offering">
            <FormField label="Core Product/Service">
              <Textarea
                value={formData.coreProduct}
                onChange={(e) => updateField('coreProduct', e.target.value)}
                rows={3}
                placeholder="Describe the main product or service..."
              />
            </FormField>
            <FormField label="Target Customer">
              <Textarea
                value={formData.targetCustomer}
                onChange={(e) => updateField('targetCustomer', e.target.value)}
                rows={2}
                placeholder="Describe the ideal customer..."
              />
            </FormField>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="ACV (Annual Contract Value)">
                <Input
                  value={formData.acv}
                  onChange={(e) => updateField('acv', e.target.value)}
                  placeholder="e.g., $10,000"
                />
              </FormField>
              <FormField label="Sales Cycle Length">
                <Input
                  value={formData.salesCycleLength}
                  onChange={(e) => updateField('salesCycleLength', e.target.value)}
                  placeholder="e.g., 30-60 days"
                />
              </FormField>
            </div>
          </Section>

          {/* Section 3: Market Signals */}
          <Section icon={Target} title="Market Signals">
            <FormField label="Buying Signals">
              <TagInput
                value={formData.signals}
                onChange={(v) => updateField('signals', v)}
                placeholder="Add a buying signal..."
              />
            </FormField>
          </Section>

          {/* Section 4: Audience */}
          <Section icon={Users} title="Audience">
            <FormField label="Target Job Titles">
              <TagInput
                value={formData.jobTitles}
                onChange={(v) => updateField('jobTitles', v)}
                placeholder="Add a job title..."
              />
            </FormField>
          </Section>

          {/* Section 5: Process */}
          <Section icon={Briefcase} title="Current Process">
            <FormField label="Outbound Tools">
              <TagInput
                value={formData.outboundTools}
                onChange={(v) => updateField('outboundTools', v)}
                placeholder="Add a tool..."
              />
            </FormField>
            <FormField label="CRM">
              <Input
                value={formData.crm}
                onChange={(e) => updateField('crm', e.target.value)}
                placeholder="e.g., Salesforce, HubSpot"
              />
            </FormField>
          </Section>

          {/* Section 6: Messaging */}
          <Section icon={MessageSquare} title="Messaging">
            <FormField label="Customer Voice">
              <Textarea
                value={formData.customerVoice}
                onChange={(e) => updateField('customerVoice', e.target.value)}
                rows={3}
                placeholder="How do customers describe your value..."
              />
            </FormField>
            <FormField label="ROI / Results">
              <Textarea
                value={formData.roiResults}
                onChange={(e) => updateField('roiResults', e.target.value)}
                rows={2}
                placeholder="Quantifiable results customers achieve..."
              />
            </FormField>
            <FormField label="Tone Style">
              <Input
                value={formData.toneStyle}
                onChange={(e) => updateField('toneStyle', e.target.value)}
                placeholder="e.g., Professional, Casual, Technical"
              />
            </FormField>
          </Section>

          {/* Section 7: Goals */}
          <Section icon={Trophy} title="Goals">
            <FormField label="Primary GTM Objective">
              <Input
                value={formData.primaryGtmObjective}
                onChange={(e) => updateField('primaryGtmObjective', e.target.value)}
                placeholder="e.g., Generate qualified leads"
              />
            </FormField>
            <FormField label="Success Metrics">
              <TagInput
                value={formData.successMetrics}
                onChange={(v) => updateField('successMetrics', v)}
                placeholder="Add a success metric..."
              />
            </FormField>
            <FormField label="Success Definition">
              <Textarea
                value={formData.successDefinition}
                onChange={(e) => updateField('successDefinition', e.target.value)}
                rows={2}
                placeholder="What does success look like..."
              />
            </FormField>
          </Section>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Changes
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
