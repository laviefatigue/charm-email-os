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
  Plus,
  Trash2,
  Globe,
  Swords,
  TrendingUp,
  BookOpen,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { onboardingApi, type OnboardingSubmission } from '@/lib/api';

interface Segment {
  id?: string;
  segmentName: string;
  revenuePercentage: number;
  uniqueCharacteristics?: string;
  painPoints?: string;
  buyingTriggers?: string;
}

interface Persona {
  id?: string;
  jobTitle: string;
  primarySegment?: string;
  seniorityLevel?: string;
  painBeforeBuying?: string;
  ahaMonent?: string;
  objections?: string;
}

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
    annualRevenue: (submission as any).annualRevenue || '',
    industry: (submission as any).industry || '',

    // Market Signals
    signals: submission.signals || [],

    // Audience
    jobTitles: submission.jobTitles || [],
    competitors: (submission as any).competitors || [],
    keyDifferentiators: (submission as any).keyDifferentiators || '',
    commonObjections: (submission as any).commonObjections || '',
    buyingTriggersGlobal: (submission as any).buyingTriggersGlobal || '',

    // Process
    outboundTools: submission.outboundTools || [],
    crm: submission.crm || '',
    monthlyVolume: (submission as any).monthlyVolume || '',
    currentOpenRate: (submission as any).currentOpenRate || '',
    currentReplyRate: (submission as any).currentReplyRate || '',
    messagesWorked: (submission as any).messagesWorked || '',
    approachesFailed: (submission as any).approachesFailed || '',

    // Messaging
    customerVoice: submission.customerVoice || '',
    roiResults: submission.roiResults || '',
    toneStyle: submission.toneStyle || '',
    caseStudies: (submission as any).caseStudies || '',
    industryJargon: (submission as any).industryJargon || '',
    coreVendors: (submission as any).coreVendors || [],

    // Goals
    primaryGtmObjective: submission.primaryGtmObjective || '',
    successMetrics: submission.successMetrics || [],
    successDefinition: submission.successDefinition || '',
    engagementWin: (submission as any).engagementWin || '',
    additionalContext: (submission as any).additionalContext || '',
  });

  // Segments state
  const [segments, setSegments] = useState<Segment[]>(
    (submission as any).segments?.map((s: any) => ({
      id: s.id,
      segmentName: s.segmentName || s.segment_name || '',
      revenuePercentage: s.revenuePercentage || s.revenue_percentage || 0,
      uniqueCharacteristics: s.uniqueCharacteristics || s.unique_characteristics || '',
      painPoints: s.painPoints || s.pain_points || '',
      buyingTriggers: s.buyingTriggers || s.buying_triggers || '',
    })) || []
  );

  // Personas state
  const [personas, setPersonas] = useState<Persona[]>(
    (submission as any).personas?.map((p: any) => ({
      id: p.id,
      jobTitle: p.jobTitle || p.job_title || '',
      primarySegment: p.primarySegment || p.primary_segment || '',
      seniorityLevel: p.seniorityLevel || p.seniority_level || '',
      painBeforeBuying: p.painBeforeBuying || p.pain_before_buying || '',
      ahaMonent: p.ahaMonent || p.aha_moment || '',
      objections: p.objections || '',
    })) || []
  );

  const updateField = (field: string, value: string | string[]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      // Convert camelCase to snake_case for API
      const updatePayload = {
        // Foundation
        company_name: formData.companyName || undefined,
        website: formData.website || undefined,
        contact_name: formData.contactName || undefined,
        contact_email: formData.contactEmail || undefined,
        employee_count: formData.employeeCount || undefined,
        funding_stage: formData.fundingStage || undefined,
        hq_location: formData.hqLocation || undefined,

        // Offering
        core_product: formData.coreProduct || undefined,
        target_customer: formData.targetCustomer || undefined,
        acv: formData.acv || undefined,
        sales_cycle_length: formData.salesCycleLength || undefined,
        annual_revenue: formData.annualRevenue || undefined,
        industry: formData.industry || undefined,

        // Market Signals
        signals: formData.signals.length > 0 ? formData.signals : undefined,

        // Audience
        job_titles: formData.jobTitles.length > 0 ? formData.jobTitles : undefined,
        competitors: formData.competitors.length > 0 ? formData.competitors : undefined,
        key_differentiators: formData.keyDifferentiators || undefined,
        common_objections: formData.commonObjections || undefined,
        buying_triggers_global: formData.buyingTriggersGlobal || undefined,

        // Segments and Personas (convert back to snake_case)
        segments: segments.length > 0 ? segments.map(s => ({
          id: s.id,
          segment_name: s.segmentName,
          revenue_percentage: s.revenuePercentage,
          unique_characteristics: s.uniqueCharacteristics,
          pain_points: s.painPoints,
          buying_triggers: s.buyingTriggers,
        })) : undefined,
        personas: personas.length > 0 ? personas.map(p => ({
          id: p.id,
          job_title: p.jobTitle,
          primary_segment: p.primarySegment,
          seniority_level: p.seniorityLevel,
          pain_before_buying: p.painBeforeBuying,
          aha_moment: p.ahaMonent,
          objections: p.objections,
        })) : undefined,

        // Process
        outbound_tools: formData.outboundTools.length > 0 ? formData.outboundTools : undefined,
        crm: formData.crm || undefined,
        monthly_volume: formData.monthlyVolume || undefined,
        current_open_rate: formData.currentOpenRate || undefined,
        current_reply_rate: formData.currentReplyRate || undefined,
        messages_worked: formData.messagesWorked || undefined,
        approaches_failed: formData.approachesFailed || undefined,

        // Messaging
        customer_voice: formData.customerVoice || undefined,
        roi_results: formData.roiResults || undefined,
        tone_style: formData.toneStyle || undefined,
        case_studies: formData.caseStudies || undefined,
        industry_jargon: formData.industryJargon || undefined,
        core_vendors: formData.coreVendors.length > 0 ? formData.coreVendors : undefined,

        // Goals
        primary_gtm_objective: formData.primaryGtmObjective || undefined,
        success_metrics: formData.successMetrics.length > 0 ? formData.successMetrics : undefined,
        success_definition: formData.successDefinition || undefined,
        engagement_win: formData.engagementWin || undefined,
        additional_context: formData.additionalContext || undefined,
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

  // Helper functions for segments
  const addSegment = () => {
    setSegments([...segments, {
      segmentName: '',
      revenuePercentage: 0,
      uniqueCharacteristics: '',
      painPoints: '',
      buyingTriggers: '',
    }]);
  };

  const updateSegment = (index: number, field: keyof Segment, value: string | number) => {
    const updated = [...segments];
    (updated[index] as any)[field] = value;
    setSegments(updated);
  };

  const removeSegment = (index: number) => {
    setSegments(segments.filter((_, i) => i !== index));
  };

  // Helper functions for personas
  const addPersona = () => {
    setPersonas([...personas, {
      jobTitle: '',
      primarySegment: '',
      seniorityLevel: '',
      painBeforeBuying: '',
      ahaMonent: '',
      objections: '',
    }]);
  };

  const updatePersona = (index: number, field: keyof Persona, value: string) => {
    const updated = [...personas];
    (updated[index] as any)[field] = value;
    setPersonas(updated);
  };

  const removePersona = (index: number) => {
    setPersonas(personas.filter((_, i) => i !== index));
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
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Industry / Vertical">
                <Select
                  value={formData.industry}
                  onValueChange={(v) => updateField('industry', v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select industry..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="SaaS">SaaS</SelectItem>
                    <SelectItem value="Financial Services">Financial Services</SelectItem>
                    <SelectItem value="Healthcare">Healthcare</SelectItem>
                    <SelectItem value="E-commerce">E-commerce</SelectItem>
                    <SelectItem value="Manufacturing">Manufacturing</SelectItem>
                    <SelectItem value="Professional Services">Professional Services</SelectItem>
                    <SelectItem value="Real Estate">Real Estate</SelectItem>
                    <SelectItem value="Education">Education</SelectItem>
                    <SelectItem value="Fintech">Fintech</SelectItem>
                    <SelectItem value="Other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label="Annual Revenue">
                <Select
                  value={formData.annualRevenue}
                  onValueChange={(v) => updateField('annualRevenue', v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select range..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="<$1M">&lt;$1M</SelectItem>
                    <SelectItem value="$1M-$5M">$1M-$5M</SelectItem>
                    <SelectItem value="$5M-$20M">$5M-$20M</SelectItem>
                    <SelectItem value="$20M+">$20M+</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            </div>
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

            {/* Segments */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Customer Segments
                </Label>
                <Button type="button" variant="outline" size="sm" onClick={addSegment}>
                  <Plus className="h-3 w-3 mr-1" /> Add Segment
                </Button>
              </div>
              {segments.map((segment, idx) => (
                <div key={idx} className="border rounded-lg p-3 space-y-2 bg-muted/30">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Segment {idx + 1}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeSegment(idx)}
                      className="h-6 w-6 p-0 text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      value={segment.segmentName}
                      onChange={(e) => updateSegment(idx, 'segmentName', e.target.value)}
                      placeholder="Segment name..."
                    />
                    <Input
                      type="number"
                      value={segment.revenuePercentage}
                      onChange={(e) => updateSegment(idx, 'revenuePercentage', parseInt(e.target.value) || 0)}
                      placeholder="Revenue %"
                      min={0}
                      max={100}
                    />
                  </div>
                  <Input
                    value={segment.painPoints || ''}
                    onChange={(e) => updateSegment(idx, 'painPoints', e.target.value)}
                    placeholder="Pain points..."
                  />
                </div>
              ))}
            </div>

            {/* Personas */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Buyer Personas
                </Label>
                <Button type="button" variant="outline" size="sm" onClick={addPersona}>
                  <Plus className="h-3 w-3 mr-1" /> Add Persona
                </Button>
              </div>
              {personas.map((persona, idx) => (
                <div key={idx} className="border rounded-lg p-3 space-y-2 bg-muted/30">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Persona {idx + 1}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removePersona(idx)}
                      className="h-6 w-6 p-0 text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      value={persona.jobTitle}
                      onChange={(e) => updatePersona(idx, 'jobTitle', e.target.value)}
                      placeholder="Job title..."
                    />
                    <Input
                      value={persona.seniorityLevel || ''}
                      onChange={(e) => updatePersona(idx, 'seniorityLevel', e.target.value)}
                      placeholder="Seniority (e.g., VP, Director)"
                    />
                  </div>
                  <Input
                    value={persona.painBeforeBuying || ''}
                    onChange={(e) => updatePersona(idx, 'painBeforeBuying', e.target.value)}
                    placeholder="Pain before buying..."
                  />
                  <Input
                    value={persona.objections || ''}
                    onChange={(e) => updatePersona(idx, 'objections', e.target.value)}
                    placeholder="Common objections..."
                  />
                </div>
              ))}
            </div>
          </Section>

          {/* Section 4b: Competitive Landscape */}
          <Section icon={Swords} title="Competitive Landscape">
            <FormField label="Competitors">
              <TagInput
                value={formData.competitors}
                onChange={(v) => updateField('competitors', v)}
                placeholder="Add a competitor..."
              />
            </FormField>
            <FormField label="Key Differentiators">
              <Textarea
                value={formData.keyDifferentiators}
                onChange={(e) => updateField('keyDifferentiators', e.target.value)}
                rows={2}
                placeholder="What sets you apart from competitors..."
              />
            </FormField>
            <FormField label="Common Objections">
              <Textarea
                value={formData.commonObjections}
                onChange={(e) => updateField('commonObjections', e.target.value)}
                rows={2}
                placeholder="Typical pushback from prospects..."
              />
            </FormField>
            <FormField label="Buying Triggers">
              <Textarea
                value={formData.buyingTriggersGlobal}
                onChange={(e) => updateField('buyingTriggersGlobal', e.target.value)}
                rows={2}
                placeholder="What initiates buying behavior..."
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
            <div className="grid grid-cols-2 gap-4">
              <FormField label="CRM">
                <Input
                  value={formData.crm}
                  onChange={(e) => updateField('crm', e.target.value)}
                  placeholder="e.g., Salesforce, HubSpot"
                />
              </FormField>
              <FormField label="Monthly Email Volume">
                <Select
                  value={formData.monthlyVolume}
                  onValueChange={(v) => updateField('monthlyVolume', v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select volume..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="<1K">&lt;1K</SelectItem>
                    <SelectItem value="1K-5K">1K-5K</SelectItem>
                    <SelectItem value="5K-20K">5K-20K</SelectItem>
                    <SelectItem value="20K+">20K+</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Current Open Rate">
                <Input
                  value={formData.currentOpenRate}
                  onChange={(e) => updateField('currentOpenRate', e.target.value)}
                  placeholder="e.g., 45%"
                />
              </FormField>
              <FormField label="Current Reply Rate">
                <Input
                  value={formData.currentReplyRate}
                  onChange={(e) => updateField('currentReplyRate', e.target.value)}
                  placeholder="e.g., 3%"
                />
              </FormField>
            </div>
          </Section>

          {/* Section 5b: What's Worked / What Hasn't */}
          <Section icon={TrendingUp} title="What's Worked & What Hasn't">
            <FormField label="Messages That Have Worked">
              <Textarea
                value={formData.messagesWorked}
                onChange={(e) => updateField('messagesWorked', e.target.value)}
                rows={3}
                placeholder="What messaging approaches have been successful..."
              />
            </FormField>
            <FormField label="Approaches That Failed">
              <Textarea
                value={formData.approachesFailed}
                onChange={(e) => updateField('approachesFailed', e.target.value)}
                rows={3}
                placeholder="What approaches to avoid..."
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
            <FormField label="Case Studies (by segment)">
              <Textarea
                value={formData.caseStudies}
                onChange={(e) => updateField('caseStudies', e.target.value)}
                rows={3}
                placeholder="Case study summaries with company names and results..."
              />
            </FormField>
            <FormField label="Tone Style">
              <Select
                value={formData.toneStyle}
                onValueChange={(v) => updateField('toneStyle', v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select tone..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Professional & formal">Professional & formal</SelectItem>
                  <SelectItem value="Friendly & conversational">Friendly & conversational</SelectItem>
                  <SelectItem value="Direct & no-nonsense">Direct & no-nonsense</SelectItem>
                  <SelectItem value="Witty & playful">Witty & playful</SelectItem>
                  <SelectItem value="Technical & precise">Technical & precise</SelectItem>
                </SelectContent>
              </Select>
            </FormField>
            <FormField label="Industry Jargon (terms to use or avoid)">
              <Textarea
                value={formData.industryJargon}
                onChange={(e) => updateField('industryJargon', e.target.value)}
                rows={2}
                placeholder="Industry-specific terms to use or avoid..."
              />
            </FormField>
          </Section>

          {/* Section 6b: Tech Stack */}
          <Section icon={Globe} title="Tech Stack / Core Vendors">
            <FormField label="Core Vendors (for targeting)">
              <TagInput
                value={formData.coreVendors}
                onChange={(v) => updateField('coreVendors', v)}
                placeholder="Add a vendor (e.g., Salesforce, Fiserv)..."
              />
            </FormField>
          </Section>

          {/* Section 7: Goals */}
          <Section icon={Trophy} title="Goals">
            <FormField label="Primary GTM Objective">
              <Select
                value={formData.primaryGtmObjective}
                onValueChange={(v) => updateField('primaryGtmObjective', v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select objective..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Pipeline Generation">Pipeline Generation</SelectItem>
                  <SelectItem value="Brand Awareness">Brand Awareness</SelectItem>
                  <SelectItem value="Market Expansion">Market Expansion</SelectItem>
                  <SelectItem value="Product Launch">Product Launch</SelectItem>
                  <SelectItem value="Competitive Displacement">Competitive Displacement</SelectItem>
                  <SelectItem value="Account Expansion">Account Expansion</SelectItem>
                </SelectContent>
              </Select>
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
            <FormField label="What Would Be a Win">
              <Textarea
                value={formData.engagementWin}
                onChange={(e) => updateField('engagementWin', e.target.value)}
                rows={2}
                placeholder="What outcome would make this engagement a success..."
              />
            </FormField>
            <FormField label="Additional Context">
              <Textarea
                value={formData.additionalContext}
                onChange={(e) => updateField('additionalContext', e.target.value)}
                rows={3}
                placeholder="Any additional context or notes..."
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
