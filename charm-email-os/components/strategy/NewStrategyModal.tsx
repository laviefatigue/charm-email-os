'use client';

import { useState } from 'react';
import { Loader2, FileEdit, Link2, Copy, Check, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { strategyApi, type Strategy } from '@/lib/api';
import { toast } from 'sonner';

interface NewStrategyModalProps {
  clientId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStrategyCreated: (strategy: Strategy) => void;
}

type CreationMode = 'select' | 'fill-myself' | 'send-link';

interface StrategyFormData {
  name: string;
  description: string;
  // Offering section
  coreProduct: string;
  targetCustomer: string;
  acv: string;
  salesCycle: string;
  // Audience section
  jobTitles: string;
  segments: string;
  // Messaging section
  customerVoice: string;
  roiResults: string;
  toneStyle: string;
  // Goals section
  primaryGtmObjective: string;
  successMetrics: string;
}

const initialFormData: StrategyFormData = {
  name: '',
  description: '',
  coreProduct: '',
  targetCustomer: '',
  acv: '',
  salesCycle: '',
  jobTitles: '',
  segments: '',
  customerVoice: '',
  roiResults: '',
  toneStyle: '',
  primaryGtmObjective: '',
  successMetrics: '',
};

export function NewStrategyModal({
  clientId,
  open,
  onOpenChange,
  onStrategyCreated,
}: NewStrategyModalProps) {
  const [mode, setMode] = useState<CreationMode>('select');
  const [formData, setFormData] = useState<StrategyFormData>(initialFormData);
  const [creating, setCreating] = useState(false);
  const [shareableLink, setShareableLink] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [currentSection, setCurrentSection] = useState<string>('offering');

  const resetModal = () => {
    setMode('select');
    setFormData(initialFormData);
    setShareableLink(null);
    setLinkCopied(false);
    setCurrentSection('offering');
  };

  const handleClose = () => {
    onOpenChange(false);
    setTimeout(resetModal, 200); // Reset after close animation
  };

  const updateFormData = (field: keyof StrategyFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleCreateWithForm = async () => {
    if (!formData.name.trim()) {
      toast.error('Please enter a strategy name');
      return;
    }

    setCreating(true);
    try {
      // Create strategy first
      const strategy = await strategyApi.createStrategy(
        clientId,
        formData.name.trim(),
        formData.description.trim() || undefined
      );

      // TODO: Create submission with form data and link to strategy
      // For now, just create the strategy without the submission
      // This would require a new API endpoint that creates both

      onStrategyCreated(strategy);
      toast.success('Strategy created');
      handleClose();
    } catch (err) {
      console.error('Failed to create strategy:', err);
      toast.error('Failed to create strategy');
    } finally {
      setCreating(false);
    }
  };

  const handleGenerateLink = async () => {
    if (!formData.name.trim()) {
      toast.error('Please enter a strategy name');
      return;
    }

    setCreating(true);
    try {
      // Create strategy with pending_submission status
      const strategy = await strategyApi.createStrategy(
        clientId,
        formData.name.trim(),
        formData.description.trim() || undefined
      );

      // TODO: Generate shareable link via backend
      // For now, use a placeholder - this would require a new endpoint
      const baseUrl = window.location.origin;
      const link = `${baseUrl}/onboarding/strategy/${strategy.id}`;
      setShareableLink(link);

      onStrategyCreated(strategy);
      toast.success('Strategy created - share the link with your client');
    } catch (err) {
      console.error('Failed to create strategy:', err);
      toast.error('Failed to create strategy');
    } finally {
      setCreating(false);
    }
  };

  const handleCopyLink = async () => {
    if (!shareableLink) return;
    try {
      await navigator.clipboard.writeText(shareableLink);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      toast.success('Link copied to clipboard');
    } catch (err) {
      toast.error('Failed to copy link');
    }
  };

  const renderModeSelection = () => (
    <div className="space-y-4 py-4">
      <div className="grid gap-2">
        <Label htmlFor="strategy-name">Strategy Name</Label>
        <Input
          id="strategy-name"
          placeholder="e.g., Q1 Outreach Campaign"
          value={formData.name}
          onChange={(e) => updateFormData('name', e.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="strategy-description">Description (optional)</Label>
        <Input
          id="strategy-description"
          placeholder="Brief description of this strategy"
          value={formData.description}
          onChange={(e) => updateFormData('description', e.target.value)}
        />
      </div>

      <div className="pt-4">
        <Label className="text-sm text-muted-foreground mb-3 block">
          How would you like to provide strategy details?
        </Label>
        <div className="grid grid-cols-2 gap-4">
          <Card
            className="cursor-pointer hover:border-primary transition-colors"
            onClick={() => setMode('fill-myself')}
          >
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center gap-2">
                <FileEdit className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">Fill it myself</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <CardDescription className="text-xs">
                I&apos;ll fill out the 4-section form with offering, audience, messaging, and goals
              </CardDescription>
            </CardContent>
          </Card>

          <Card
            className="cursor-pointer hover:border-primary transition-colors"
            onClick={() => setMode('send-link')}
          >
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center gap-2">
                <Link2 className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">Send link to client</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <CardDescription className="text-xs">
                Generate a shareable link for my client to complete
              </CardDescription>
            </CardContent>
          </Card>
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center pt-2">
        Foundation data (company, contact info) will be inherited from the most recent submission.
      </p>
    </div>
  );

  const renderFillMyselfForm = () => (
    <div className="space-y-4 py-4">
      <Tabs value={currentSection} onValueChange={setCurrentSection}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="offering">Offering</TabsTrigger>
          <TabsTrigger value="audience">Audience</TabsTrigger>
          <TabsTrigger value="messaging">Messaging</TabsTrigger>
          <TabsTrigger value="goals">Goals</TabsTrigger>
        </TabsList>

        <TabsContent value="offering" className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label>Core Product/Service</Label>
            <Textarea
              placeholder="What are you selling? Describe the main offering..."
              value={formData.coreProduct}
              onChange={(e) => updateFormData('coreProduct', e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label>Target Customer</Label>
            <Input
              placeholder="Who is the ideal buyer?"
              value={formData.targetCustomer}
              onChange={(e) => updateFormData('targetCustomer', e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Average Contract Value</Label>
              <Input
                placeholder="e.g., $50,000"
                value={formData.acv}
                onChange={(e) => updateFormData('acv', e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Sales Cycle Length</Label>
              <Input
                placeholder="e.g., 3-6 months"
                value={formData.salesCycle}
                onChange={(e) => updateFormData('salesCycle', e.target.value)}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="audience" className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label>Job Titles to Target</Label>
            <Textarea
              placeholder="VP of Sales, Head of Marketing, CRO..."
              value={formData.jobTitles}
              onChange={(e) => updateFormData('jobTitles', e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label>Market Segments (optional)</Label>
            <Textarea
              placeholder="Industry verticals, company sizes, regions..."
              value={formData.segments}
              onChange={(e) => updateFormData('segments', e.target.value)}
              rows={2}
            />
          </div>
        </TabsContent>

        <TabsContent value="messaging" className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label>Customer Voice / Testimonials</Label>
            <Textarea
              placeholder="What do customers say about you? Include quotes if available..."
              value={formData.customerVoice}
              onChange={(e) => updateFormData('customerVoice', e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label>ROI / Results</Label>
            <Textarea
              placeholder="What results have customers achieved? Include metrics..."
              value={formData.roiResults}
              onChange={(e) => updateFormData('roiResults', e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label>Tone/Style Preferences</Label>
            <Input
              placeholder="e.g., Professional but conversational, data-driven..."
              value={formData.toneStyle}
              onChange={(e) => updateFormData('toneStyle', e.target.value)}
            />
          </div>
        </TabsContent>

        <TabsContent value="goals" className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label>Primary GTM Objective</Label>
            <Textarea
              placeholder="What's the main goal? (e.g., Book demos, start trials, schedule calls...)"
              value={formData.primaryGtmObjective}
              onChange={(e) => updateFormData('primaryGtmObjective', e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label>Success Metrics</Label>
            <Textarea
              placeholder="How will you measure success? (e.g., reply rate, meetings booked...)"
              value={formData.successMetrics}
              onChange={(e) => updateFormData('successMetrics', e.target.value)}
              rows={2}
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );

  const renderSendLinkForm = () => (
    <div className="space-y-4 py-4">
      {!shareableLink ? (
        <>
          <p className="text-sm text-muted-foreground">
            We&apos;ll generate a unique link that you can send to your client. They&apos;ll fill out the strategy details directly.
          </p>
          <div className="bg-muted p-4 rounded-lg">
            <p className="text-sm font-medium mb-2">What the client will provide:</p>
            <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
              <li>Core offering and target customer</li>
              <li>Job titles and segments to target</li>
              <li>Messaging preferences and testimonials</li>
              <li>Campaign goals and success metrics</li>
            </ul>
          </div>
        </>
      ) : (
        <div className="space-y-4">
          <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-lg border border-green-200 dark:border-green-800">
            <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">
              Link generated successfully!
            </p>
            <div className="flex items-center gap-2">
              <Input
                value={shareableLink}
                readOnly
                className="bg-white dark:bg-background text-sm"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyLink}
                className="shrink-0"
              >
                {linkCopied ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Share this link with your client. Once they complete the form, the strategy will be ready for email generation.
          </p>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => window.open(shareableLink, '_blank')}
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Preview Link
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {mode === 'select' && 'Create New Strategy'}
            {mode === 'fill-myself' && 'Strategy Details'}
            {mode === 'send-link' && 'Send Link to Client'}
          </DialogTitle>
          <DialogDescription>
            {mode === 'select' && 'Create a new strategy to organize campaign variants'}
            {mode === 'fill-myself' && `Strategy: ${formData.name || 'Untitled'}`}
            {mode === 'send-link' && `Strategy: ${formData.name || 'Untitled'}`}
          </DialogDescription>
        </DialogHeader>

        {mode === 'select' && renderModeSelection()}
        {mode === 'fill-myself' && renderFillMyselfForm()}
        {mode === 'send-link' && renderSendLinkForm()}

        <DialogFooter>
          {mode === 'select' && (
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          )}

          {mode === 'fill-myself' && (
            <>
              <Button variant="outline" onClick={() => setMode('select')}>
                Back
              </Button>
              <Button
                onClick={handleCreateWithForm}
                disabled={creating || !formData.name.trim()}
              >
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Creating...
                  </>
                ) : (
                  'Create Strategy'
                )}
              </Button>
            </>
          )}

          {mode === 'send-link' && (
            <>
              {!shareableLink ? (
                <>
                  <Button variant="outline" onClick={() => setMode('select')}>
                    Back
                  </Button>
                  <Button
                    onClick={handleGenerateLink}
                    disabled={creating || !formData.name.trim()}
                  >
                    {creating ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Generating...
                      </>
                    ) : (
                      'Generate Link'
                    )}
                  </Button>
                </>
              ) : (
                <Button onClick={handleClose}>Done</Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
