'use client';

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { nanoid } from 'nanoid';
import {
  Target,
  Database,
  FileText,
  Mail,
  Plus,
  X,
  Trash2,
  Sparkles,
  Wand2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useStrategyStore } from '@/lib/stores';
import type {
  Client,
  CampaignIdea,
  CampaignType,
  ClayVariables,
  EmailCopy,
  CreativeIdea,
  FollowUpEmail,
} from '@/lib/types';
import { INDUSTRIES } from '@/lib/types';
import { cn } from '@/lib/utils';

interface CreateCampaignModalProps {
  client: Client;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CAMPAIGN_TYPES: { value: CampaignType; label: string; description: string }[] = [
  { value: 'custom_signal', label: 'Custom Signal', description: 'High-signal personalization based on specific prospect data' },
  { value: 'creative_ideas', label: 'Creative Ideas', description: 'Feature-constrained creative concepts' },
  { value: 'whole_offer', label: 'Whole Offer', description: 'Complete value proposition approach' },
  { value: 'fallback', label: 'Fallback', description: 'Generic but compelling outreach' },
];

// Campaign templates based on type
const CAMPAIGN_TEMPLATES: Record<CampaignType, Partial<CampaignIdea>> = {
  custom_signal: {
    title: 'Custom Signal Campaign',
    angle: 'Leverage high-signal data points (tenure, hiring, tech stack) to create highly relevant outreach.',
    icpDescription: '',
    valueProposition: {
      business: '',
      personal: '',
    },
    objections: [],
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}', roleTitle: '{{role_title}}' },
      highSignal: {},
      aiGenerated: {},
      custom: {},
      caseStudy: {},
    },
    email1: {
      subject: '{{first_name}}, quick question about {{company_name}}',
      body: `Hi {{first_name}},

[Opening with specific signal/observation]

[Value proposition relevant to their situation]

[Low-friction CTA]`,
      cta: 'Worth a quick chat?',
    },
  },
  creative_ideas: {
    title: 'Creative Ideas Campaign',
    angle: 'Generate feature-constrained creative concepts that resonate with specific prospect pain points.',
    icpDescription: '',
    valueProposition: {
      business: '',
      personal: '',
    },
    objections: [],
    constraintBox: [],
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: {},
      aiGenerated: { customerType: '{{ai_customer_type}}' },
      custom: {},
      caseStudy: {},
    },
    creativeIdeas: [],
    email1: {
      subject: 'Idea for {{company_name}}',
      body: `{{first_name}},

Had an idea specifically for {{company_name}}:

[Creative idea using feature constraint]

[How it would benefit them]

[Soft CTA]`,
      cta: 'Interested in hearing more?',
    },
  },
  whole_offer: {
    title: 'Whole Offer Campaign',
    angle: 'Present the complete value proposition in a compelling way that addresses both business and personal wins.',
    icpDescription: '',
    valueProposition: {
      business: '',
      personal: '',
    },
    objections: [],
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}', roleTitle: '{{role_title}}' },
      highSignal: {},
      aiGenerated: {},
      custom: {},
      caseStudy: {},
    },
    email1: {
      subject: '{{role_title}}s at {{company_name}} typically see...',
      body: `Hi {{first_name}},

[Problem statement relevant to their role]

[How we solve it - whole offer summary]

[Social proof / case study teaser]

[Clear CTA]`,
      cta: 'Open to a brief call this week?',
    },
  },
  fallback: {
    title: 'Fallback Campaign',
    angle: 'Generic but compelling outreach for prospects without strong signals. Focus on common pain points.',
    icpDescription: '',
    valueProposition: {
      business: '',
      personal: '',
    },
    objections: [],
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: {},
      aiGenerated: {},
      custom: {},
      caseStudy: {},
    },
    email1: {
      subject: 'Quick question',
      body: `Hi {{first_name}},

[Common industry pain point]

[Brief value prop]

[Simple CTA]`,
      cta: 'Worth exploring?',
    },
  },
};

const DEFAULT_EMAIL: EmailCopy = { subject: '', body: '', cta: '' };
const DEFAULT_CREATIVE_IDEA: CreativeIdea = { feature: '', action: '', target: '', benefit: '' };
const DEFAULT_FOLLOWUP: FollowUpEmail = { day: 3, copy: { ...DEFAULT_EMAIL }, angle: '' };

export function CreateCampaignModal({ client, open, onOpenChange }: CreateCampaignModalProps) {
  // Strategy Tab State
  const [campaignType, setCampaignType] = useState<CampaignType>('custom_signal');
  const [industry, setIndustry] = useState('');
  const [segment, setSegment] = useState('');
  const [title, setTitle] = useState('');
  const [angle, setAngle] = useState('');
  const [icpDescription, setIcpDescription] = useState('');
  const [businessValue, setBusinessValue] = useState('');
  const [personalValue, setPersonalValue] = useState('');
  const [objections, setObjections] = useState<string[]>([]);
  const [objectionInput, setObjectionInput] = useState('');

  // Variables Tab State
  const [constraintBox, setConstraintBox] = useState<string[]>([]);
  const [constraintInput, setConstraintInput] = useState('');
  const [variables, setVariables] = useState<ClayVariables>({
    core: {},
    highSignal: {},
    aiGenerated: {},
    custom: {},
    caseStudy: {},
  });

  // Copy Tab State
  const [email1, setEmail1] = useState<EmailCopy>({ ...DEFAULT_EMAIL });
  const [creativeIdeas, setCreativeIdeas] = useState<CreativeIdea[]>([]);

  // Sequence Tab State
  const [followUps, setFollowUps] = useState<FollowUpEmail[]>([]);

  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('strategy');

  const { updateIdea, setIdeas, ideas } = useStrategyStore();

  // Initialize with client data and template when modal opens
  useEffect(() => {
    if (open && client) {
      // Pre-fill with client onboarding data
      const onboarding = client.onboardingData;
      if (onboarding) {
        setIndustry(onboarding.industry || '');
        setSegment('');
        setIcpDescription(onboarding.product || '');
      } else {
        setIndustry('');
        setSegment('');
        setIcpDescription('');
      }

      // Apply default template
      applyTemplate('custom_signal');
      setActiveTab('strategy');
    }
  }, [open, client]);

  // Apply template when campaign type changes
  const applyTemplate = (type: CampaignType) => {
    const template = CAMPAIGN_TEMPLATES[type];
    setCampaignType(type);
    setTitle(template.title || '');
    setAngle(template.angle || '');
    setBusinessValue(template.valueProposition?.business || '');
    setPersonalValue(template.valueProposition?.personal || '');
    setObjections(template.objections || []);
    setConstraintBox(template.constraintBox || []);
    setVariables(template.variables || {
      core: {},
      highSignal: {},
      aiGenerated: {},
      custom: {},
      caseStudy: {},
    });
    setEmail1(template.email1 || { ...DEFAULT_EMAIL });
    setCreativeIdeas(template.creativeIdeas || []);
    setFollowUps([]);
  };

  const handleTypeChange = (type: CampaignType) => {
    applyTemplate(type);
  };

  // Tag input handlers
  const handleAddObjection = () => {
    const val = objectionInput.trim();
    if (val && !objections.includes(val)) {
      setObjections([...objections, val]);
      setObjectionInput('');
    }
  };

  const handleRemoveObjection = (obj: string) => {
    setObjections(objections.filter((o) => o !== obj));
  };

  const handleAddConstraint = () => {
    const val = constraintInput.trim();
    if (val && !constraintBox.includes(val)) {
      setConstraintBox([...constraintBox, val]);
      setConstraintInput('');
    }
  };

  const handleRemoveConstraint = (c: string) => {
    setConstraintBox(constraintBox.filter((x) => x !== c));
  };

  // Creative Ideas handlers
  const handleAddCreativeIdea = () => {
    setCreativeIdeas([...creativeIdeas, { ...DEFAULT_CREATIVE_IDEA }]);
  };

  const handleUpdateCreativeIdea = (index: number, field: keyof CreativeIdea, value: string) => {
    const updated = [...creativeIdeas];
    updated[index] = { ...updated[index], [field]: value };
    setCreativeIdeas(updated);
  };

  const handleRemoveCreativeIdea = (index: number) => {
    setCreativeIdeas(creativeIdeas.filter((_, i) => i !== index));
  };

  // Follow-up handlers
  const handleAddFollowUp = () => {
    const lastDay = followUps.length > 0 ? followUps[followUps.length - 1].day : 0;
    setFollowUps([...followUps, { ...DEFAULT_FOLLOWUP, day: lastDay + 3 }]);
  };

  const handleUpdateFollowUp = (index: number, updates: Partial<FollowUpEmail>) => {
    const updated = [...followUps];
    updated[index] = { ...updated[index], ...updates };
    setFollowUps(updated);
  };

  const handleRemoveFollowUp = (index: number) => {
    setFollowUps(followUps.filter((_, i) => i !== index));
  };

  // Variable update helper
  const updateVariable = (
    category: 'core' | 'highSignal' | 'aiGenerated' | 'caseStudy',
    key: string,
    value: string
  ) => {
    setVariables((prev) => ({
      ...prev,
      [category]: {
        ...prev[category],
        [key]: value || undefined,
      },
    }));
  };

  // Custom variable handlers
  const [customVarKey, setCustomVarKey] = useState('');
  const [customVarValue, setCustomVarValue] = useState('');

  const handleAddCustomVariable = () => {
    if (customVarKey.trim() && customVarValue.trim()) {
      setVariables((prev) => ({
        ...prev,
        custom: {
          ...prev.custom,
          [customVarKey.trim()]: customVarValue.trim(),
        },
      }));
      setCustomVarKey('');
      setCustomVarValue('');
    }
  };

  const handleRemoveCustomVariable = (key: string) => {
    setVariables((prev) => {
      const { [key]: _, ...rest } = prev.custom || {};
      return { ...prev, custom: rest };
    });
  };

  const handleSubmit = async () => {
    if (!industry || !segment.trim() || !title.trim() || !angle.trim()) {
      toast.error('Please fill in required fields (Industry, Segment, Title, Angle)');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    const newCampaign: CampaignIdea = {
      id: nanoid(),
      clientId: client.id,
      // Strategy
      campaignType,
      industry,
      segment: segment.trim(),
      title: title.trim(),
      angle: angle.trim(),
      icpDescription: icpDescription.trim() || undefined,
      valueProposition:
        businessValue.trim() || personalValue.trim()
          ? { business: businessValue.trim(), personal: personalValue.trim() }
          : undefined,
      objections: objections.length > 0 ? objections : undefined,

      // Variables
      constraintBox: constraintBox.length > 0 ? constraintBox : undefined,
      variables:
        Object.keys(variables.core || {}).length > 0 ||
        Object.keys(variables.highSignal || {}).length > 0 ||
        Object.keys(variables.aiGenerated || {}).length > 0 ||
        Object.keys(variables.custom || {}).length > 0 ||
        Object.keys(variables.caseStudy || {}).length > 0
          ? variables
          : undefined,

      // Copy
      email1:
        email1.subject.trim() || email1.body.trim() || email1.cta.trim()
          ? {
              subject: email1.subject.trim(),
              body: email1.body.trim(),
              cta: email1.cta.trim(),
            }
          : undefined,
      creativeIdeas: creativeIdeas.length > 0 ? creativeIdeas : undefined,

      // Sequence
      followUps: followUps.length > 0 ? followUps : undefined,

      // Meta
      status: 'pending',
      generatedAt: new Date(),
    };

    // Add to store
    setIdeas([...ideas, newCampaign]);

    toast.success('Campaign created and ready for approval!');

    setLoading(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="h-5 w-5" />
            Create New Campaign
          </DialogTitle>
          <DialogDescription>
            Create a manual campaign for {client.name}. Choose a campaign type to start with a template.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 overflow-hidden flex flex-col">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="strategy" className="gap-1.5">
              <Target className="h-4 w-4" />
              Strategy
            </TabsTrigger>
            <TabsTrigger value="variables" className="gap-1.5">
              <Database className="h-4 w-4" />
              Variables
            </TabsTrigger>
            <TabsTrigger value="copy" className="gap-1.5">
              <FileText className="h-4 w-4" />
              Copy
            </TabsTrigger>
            <TabsTrigger value="sequence" className="gap-1.5">
              <Mail className="h-4 w-4" />
              Sequence
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto py-4">
            {/* Strategy Tab */}
            <TabsContent value="strategy" className="mt-0 space-y-4">
              {/* Campaign Type with Template Selection */}
              <div className="grid gap-2">
                <Label>Campaign Type (Select to apply template)</Label>
                <Select
                  value={campaignType}
                  onValueChange={(v) => handleTypeChange(v as CampaignType)}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CAMPAIGN_TYPES.map((ct) => (
                      <SelectItem key={ct.value} value={ct.value}>
                        <div>
                          <span className="font-medium">{ct.label}</span>
                          <span className="text-muted-foreground ml-2 text-xs">
                            {ct.description}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Industry & Segment */}
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label>Industry *</Label>
                  <Select value={industry} onValueChange={setIndustry} disabled={loading}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select industry" />
                    </SelectTrigger>
                    <SelectContent>
                      {INDUSTRIES.map((ind) => (
                        <SelectItem key={ind} value={ind}>
                          {ind}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label>Target Segment *</Label>
                  <Input
                    placeholder="e.g., Series A Startups"
                    value={segment}
                    onChange={(e) => setSegment(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </div>

              {/* Title */}
              <div className="grid gap-2">
                <Label>Campaign Title *</Label>
                <Input
                  placeholder="e.g., Remote Team Pain Points"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={loading}
                />
              </div>

              {/* Angle */}
              <div className="grid gap-2">
                <Label>Campaign Angle *</Label>
                <Textarea
                  placeholder="Describe the approach and messaging strategy..."
                  value={angle}
                  onChange={(e) => setAngle(e.target.value)}
                  disabled={loading}
                  rows={3}
                />
              </div>

              {/* ICP Description */}
              <div className="grid gap-2">
                <Label>ICP Description</Label>
                <Textarea
                  placeholder="Describe the ideal customer profile for this campaign..."
                  value={icpDescription}
                  onChange={(e) => setIcpDescription(e.target.value)}
                  disabled={loading}
                  rows={2}
                />
              </div>

              {/* Value Proposition */}
              <div className="grid gap-4">
                <Label>Value Proposition</Label>
                <div className="grid grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">Business Win</Label>
                    <Input
                      placeholder="What the company gets..."
                      value={businessValue}
                      onChange={(e) => setBusinessValue(e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">Personal Win</Label>
                    <Input
                      placeholder="What they personally get..."
                      value={personalValue}
                      onChange={(e) => setPersonalValue(e.target.value)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>

              {/* Objections */}
              <div className="grid gap-2">
                <Label>Objections to Handle</Label>
                <div className="flex gap-2">
                  <Input
                    placeholder="Add an objection..."
                    value={objectionInput}
                    onChange={(e) => setObjectionInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddObjection())}
                    disabled={loading}
                    className="flex-1"
                  />
                  <Button type="button" variant="outline" onClick={handleAddObjection} disabled={loading}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                {objections.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {objections.map((obj) => (
                      <Badge key={obj} variant="secondary" className="gap-1">
                        {obj}
                        <button onClick={() => handleRemoveObjection(obj)} className="hover:text-destructive">
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            {/* Variables Tab */}
            <TabsContent value="variables" className="mt-0 space-y-6">
              {/* Constraint Box (for creative_ideas type) */}
              {campaignType === 'creative_ideas' && (
                <div className="grid gap-2">
                  <Label className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-blue-500" />
                    Constraint Box (Feature Capabilities)
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    3-5 features that creative ideas must incorporate
                  </p>
                  <div className="flex gap-2">
                    <Input
                      placeholder="Add a feature constraint..."
                      value={constraintInput}
                      onChange={(e) => setConstraintInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddConstraint())}
                      disabled={loading}
                      className="flex-1"
                    />
                    <Button type="button" variant="outline" onClick={handleAddConstraint} disabled={loading}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {constraintBox.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {constraintBox.map((c) => (
                        <Badge key={c} variant="outline" className="gap-1 bg-blue-50">
                          {c}
                          <button onClick={() => handleRemoveConstraint(c)} className="hover:text-destructive">
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Core Variables */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Core Variables</Label>
                <div className="grid grid-cols-3 gap-3">
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">First Name</Label>
                    <Input
                      placeholder="{{first_name}}"
                      value={variables.core?.firstName || ''}
                      onChange={(e) => updateVariable('core', 'firstName', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Company Name</Label>
                    <Input
                      placeholder="{{company_name}}"
                      value={variables.core?.companyName || ''}
                      onChange={(e) => updateVariable('core', 'companyName', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Role Title</Label>
                    <Input
                      placeholder="{{role_title}}"
                      value={variables.core?.roleTitle || ''}
                      onChange={(e) => updateVariable('core', 'roleTitle', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>

              {/* High-Signal Variables */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">High-Signal Variables</Label>
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Tenure Years</Label>
                    <Input
                      placeholder="{{tenure_years}}"
                      value={variables.highSignal?.tenureYears || ''}
                      onChange={(e) => updateVariable('highSignal', 'tenureYears', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Competitor</Label>
                    <Input
                      placeholder="{{competitor}}"
                      value={variables.highSignal?.competitor || ''}
                      onChange={(e) => updateVariable('highSignal', 'competitor', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Recent Post Topic</Label>
                    <Input
                      placeholder="{{recent_post_topic}}"
                      value={variables.highSignal?.recentPostTopic || ''}
                      onChange={(e) => updateVariable('highSignal', 'recentPostTopic', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Stack CRM</Label>
                    <Input
                      placeholder="{{stack_crm}}"
                      value={variables.highSignal?.stackCrm || ''}
                      onChange={(e) => updateVariable('highSignal', 'stackCrm', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>

              {/* Case Study Variables */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Case Study Variables</Label>
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Company</Label>
                    <Input
                      placeholder="{{case_study_company}}"
                      value={variables.caseStudy?.company || ''}
                      onChange={(e) => updateVariable('caseStudy', 'company', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-xs text-muted-foreground">Result</Label>
                    <Input
                      placeholder="{{case_study_result}}"
                      value={variables.caseStudy?.result || ''}
                      onChange={(e) => updateVariable('caseStudy', 'result', e.target.value)}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>

              {/* Custom Variables */}
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Custom Variables</Label>
                <div className="flex gap-2">
                  <Input
                    placeholder="Key"
                    value={customVarKey}
                    onChange={(e) => setCustomVarKey(e.target.value)}
                    disabled={loading}
                    className="w-1/3"
                  />
                  <Input
                    placeholder="Value"
                    value={customVarValue}
                    onChange={(e) => setCustomVarValue(e.target.value)}
                    disabled={loading}
                    className="flex-1"
                  />
                  <Button type="button" variant="outline" onClick={handleAddCustomVariable} disabled={loading}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                {Object.keys(variables.custom || {}).length > 0 && (
                  <div className="space-y-2 mt-2">
                    {Object.entries(variables.custom || {}).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2 text-sm bg-muted/50 rounded px-3 py-2">
                        <code className="font-mono text-primary">{`{{${key}}}`}</code>
                        <span className="text-muted-foreground">=</span>
                        <span className="flex-1 truncate">{value}</span>
                        <button onClick={() => handleRemoveCustomVariable(key)} className="text-muted-foreground hover:text-destructive">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            {/* Copy Tab */}
            <TabsContent value="copy" className="mt-0 space-y-6">
              {/* Email 1 */}
              <div className="space-y-4">
                <Label className="text-sm font-semibold flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  Email 1 Copy
                </Label>
                <div className="space-y-3 border rounded-lg p-4">
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">Subject Line</Label>
                    <Input
                      placeholder="Enter subject line..."
                      value={email1.subject}
                      onChange={(e) => setEmail1({ ...email1, subject: e.target.value })}
                      disabled={loading}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">Body</Label>
                    <Textarea
                      placeholder="Enter email body with {{variables}}..."
                      value={email1.body}
                      onChange={(e) => setEmail1({ ...email1, body: e.target.value })}
                      disabled={loading}
                      rows={6}
                      className="font-mono text-sm"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label className="text-xs text-muted-foreground">CTA</Label>
                    <Input
                      placeholder="Call to action..."
                      value={email1.cta}
                      onChange={(e) => setEmail1({ ...email1, cta: e.target.value })}
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>

              {/* Creative Ideas (for creative_ideas type) */}
              {campaignType === 'creative_ideas' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-semibold flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-blue-500" />
                      Creative Ideas
                    </Label>
                    <Button type="button" variant="outline" size="sm" onClick={handleAddCreativeIdea} disabled={loading}>
                      <Plus className="h-4 w-4 mr-1" />
                      Add Idea
                    </Button>
                  </div>
                  {creativeIdeas.length === 0 ? (
                    <p className="text-sm text-muted-foreground italic">
                      No creative ideas added yet. Click &quot;Add Idea&quot; to create one.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {creativeIdeas.map((ci, index) => (
                        <Card key={index} className="p-4 relative">
                          <button
                            onClick={() => handleRemoveCreativeIdea(index)}
                            className="absolute top-2 right-2 text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                          <div className="grid grid-cols-2 gap-3">
                            <div className="grid gap-1.5">
                              <Label className="text-xs text-muted-foreground">Feature</Label>
                              <Input
                                placeholder="Feature from constraint box"
                                value={ci.feature}
                                onChange={(e) => handleUpdateCreativeIdea(index, 'feature', e.target.value)}
                                disabled={loading}
                              />
                            </div>
                            <div className="grid gap-1.5">
                              <Label className="text-xs text-muted-foreground">Action</Label>
                              <Input
                                placeholder="What to do with it"
                                value={ci.action}
                                onChange={(e) => handleUpdateCreativeIdea(index, 'action', e.target.value)}
                                disabled={loading}
                              />
                            </div>
                            <div className="grid gap-1.5">
                              <Label className="text-xs text-muted-foreground">Target</Label>
                              <Input
                                placeholder="Who it targets"
                                value={ci.target}
                                onChange={(e) => handleUpdateCreativeIdea(index, 'target', e.target.value)}
                                disabled={loading}
                              />
                            </div>
                            <div className="grid gap-1.5">
                              <Label className="text-xs text-muted-foreground">Benefit</Label>
                              <Input
                                placeholder="Expected outcome"
                                value={ci.benefit}
                                onChange={(e) => handleUpdateCreativeIdea(index, 'benefit', e.target.value)}
                                disabled={loading}
                              />
                            </div>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            {/* Sequence Tab */}
            <TabsContent value="sequence" className="mt-0 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm font-semibold">Follow-up Sequence</Label>
                  <p className="text-xs text-muted-foreground">
                    Add follow-up emails (Email 2, 3, 4...) with different angles
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleAddFollowUp}
                  disabled={loading || followUps.length >= 4}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Follow-up
                </Button>
              </div>

              {followUps.length === 0 ? (
                <Card className="p-6 text-center">
                  <Mail className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
                  <p className="text-sm text-muted-foreground">
                    No follow-up emails configured. Click &quot;Add Follow-up&quot; to create a sequence.
                  </p>
                </Card>
              ) : (
                <div className="space-y-4">
                  {followUps.map((fu, index) => (
                    <Card key={index} className="p-4 relative">
                      <div className="flex items-center justify-between mb-3">
                        <Badge variant="outline">Email {index + 2}</Badge>
                        <button
                          onClick={() => handleRemoveFollowUp(index)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="space-y-3">
                        <div className="grid grid-cols-4 gap-3">
                          <div className="grid gap-1.5">
                            <Label className="text-xs text-muted-foreground">Day</Label>
                            <Input
                              type="number"
                              min={1}
                              value={fu.day}
                              onChange={(e) => handleUpdateFollowUp(index, { day: parseInt(e.target.value) || 1 })}
                              disabled={loading}
                            />
                          </div>
                          <div className="grid gap-1.5 col-span-3">
                            <Label className="text-xs text-muted-foreground">Subject (empty = thread)</Label>
                            <Input
                              placeholder="Leave empty to thread to previous email"
                              value={fu.subject || ''}
                              onChange={(e) => handleUpdateFollowUp(index, { subject: e.target.value || undefined })}
                              disabled={loading}
                            />
                          </div>
                        </div>
                        <div className="grid gap-1.5">
                          <Label className="text-xs text-muted-foreground">Angle</Label>
                          <Input
                            placeholder="Different value prop angle for this email"
                            value={fu.angle}
                            onChange={(e) => handleUpdateFollowUp(index, { angle: e.target.value })}
                            disabled={loading}
                          />
                        </div>
                        <div className="grid gap-1.5">
                          <Label className="text-xs text-muted-foreground">Body</Label>
                          <Textarea
                            placeholder="Email body..."
                            value={fu.copy.body}
                            onChange={(e) =>
                              handleUpdateFollowUp(index, {
                                copy: { ...fu.copy, body: e.target.value },
                              })
                            }
                            disabled={loading}
                            rows={3}
                            className="font-mono text-sm"
                          />
                        </div>
                        <div className="grid gap-1.5">
                          <Label className="text-xs text-muted-foreground">CTA</Label>
                          <Input
                            placeholder="Call to action..."
                            value={fu.copy.cta}
                            onChange={(e) =>
                              handleUpdateFollowUp(index, {
                                copy: { ...fu.copy, cta: e.target.value },
                              })
                            }
                            disabled={loading}
                          />
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="border-t pt-4">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? 'Creating...' : 'Create Campaign'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
