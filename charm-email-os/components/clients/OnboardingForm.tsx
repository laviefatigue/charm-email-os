'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { X, Check, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useClientStore } from '@/lib/stores';
import type { Client, OnboardingData } from '@/lib/types';
import { INDUSTRIES } from '@/lib/types';
import { cn } from '@/lib/utils';

interface OnboardingFormProps {
  client: Client;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete?: () => void;
}

const STEPS = [
  { id: 1, title: 'Contacts', description: 'Add contact first names for email personas' },
  { id: 2, title: 'Domain', description: 'Confirm the primary sending domain' },
  { id: 3, title: 'Industry', description: 'Select the client\'s industry' },
  { id: 4, title: 'Product', description: 'Describe the product or service' },
  { id: 5, title: 'Inboxes', description: 'How many inboxes are needed?' },
  { id: 6, title: 'Notes', description: 'Any additional requirements' },
];

export function OnboardingForm({ client, open, onOpenChange, onComplete }: OnboardingFormProps) {
  const existingData = client.onboardingData;
  const [currentStep, setCurrentStep] = useState(1);

  const [contactNames, setContactNames] = useState<string[]>(existingData?.contactFirstNames || []);
  const [contactInput, setContactInput] = useState('');
  const [primaryDomain, setPrimaryDomain] = useState(existingData?.primaryDomain || client.domain);
  const [industry, setIndustry] = useState(existingData?.industry || '');
  const [product, setProduct] = useState(existingData?.product || '');
  const [inboxesNeeded, setInboxesNeeded] = useState(existingData?.inboxesNeeded || 5);
  const [notes, setNotes] = useState(existingData?.notes || '');
  const [loading, setLoading] = useState(false);

  const { completeOnboarding } = useClientStore();

  const handleAddContact = () => {
    const name = contactInput.trim();
    if (name && !contactNames.includes(name)) {
      setContactNames([...contactNames, name]);
      setContactInput('');
    }
  };

  const handleRemoveContact = (name: string) => {
    setContactNames(contactNames.filter((n) => n !== name));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddContact();
    }
  };

  const canProceed = () => {
    switch (currentStep) {
      case 3:
        return !!industry;
      case 4:
        return !!product.trim();
      default:
        return true;
    }
  };

  const handleNext = () => {
    if (currentStep < STEPS.length) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = async () => {
    if (!industry || !product.trim()) {
      toast.error('Please fill in all required fields');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    const data: OnboardingData = {
      contactFirstNames: contactNames,
      primaryDomain,
      industry,
      product: product.trim(),
      inboxesNeeded,
      notes: notes.trim() || undefined,
    };

    completeOnboarding(client.id, data);
    toast.success("Onboarding complete! Let's set up your infrastructure.");

    setLoading(false);
    onOpenChange(false);

    if (onComplete) {
      onComplete();
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-base font-medium">Contact First Names</Label>
              <p className="text-sm text-muted-foreground mt-1">
                These names will be used as sender personas for email campaigns.
              </p>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="Enter a name and press Enter"
                value={contactInput}
                onChange={(e) => setContactInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                className="flex-1"
              />
              <Button type="button" variant="outline" onClick={handleAddContact} disabled={loading}>
                Add
              </Button>
            </div>
            {contactNames.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {contactNames.map((name) => (
                  <Badge key={name} variant="secondary" className="gap-1 px-3 py-1.5">
                    {name}
                    <button
                      type="button"
                      onClick={() => handleRemoveContact(name)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
            {contactNames.length === 0 && (
              <p className="text-sm text-muted-foreground italic">
                No contacts added yet. You can skip this step if needed.
              </p>
            )}
          </div>
        );

      case 2:
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="primaryDomain" className="text-base font-medium">Primary Domain</Label>
              <p className="text-sm text-muted-foreground mt-1">
                The main domain for sending emails. This will be used as the base for inbox setup.
              </p>
            </div>
            <Input
              id="primaryDomain"
              value={primaryDomain}
              onChange={(e) => setPrimaryDomain(e.target.value)}
              disabled={loading}
              placeholder="example.com"
            />
          </div>
        );

      case 3:
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="industry" className="text-base font-medium">Industry *</Label>
              <p className="text-sm text-muted-foreground mt-1">
                Select the industry that best describes your client. This helps generate targeted campaign angles.
              </p>
            </div>
            <Select value={industry} onValueChange={setIndustry} disabled={loading}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select an industry" />
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
        );

      case 4:
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="product" className="text-base font-medium">Product/Service Description *</Label>
              <p className="text-sm text-muted-foreground mt-1">
                Describe what your client offers and who their target audience is.
              </p>
            </div>
            <Textarea
              id="product"
              placeholder="e.g., B2B SaaS platform that helps sales teams automate outreach..."
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              disabled={loading}
              rows={4}
            />
          </div>
        );

      case 5:
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="inboxes" className="text-base font-medium">Number of Inboxes Needed</Label>
              <p className="text-sm text-muted-foreground mt-1">
                How many sending inboxes should we provision? More inboxes = higher volume capacity.
              </p>
            </div>
            <Input
              id="inboxes"
              type="number"
              min={1}
              max={50}
              value={inboxesNeeded}
              onChange={(e) => setInboxesNeeded(parseInt(e.target.value) || 1)}
              disabled={loading}
              className="w-32"
            />
            <p className="text-xs text-muted-foreground">
              Recommended: 5-10 inboxes per campaign for optimal deliverability.
            </p>
          </div>
        );

      case 6:
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="notes" className="text-base font-medium">Additional Notes</Label>
              <p className="text-sm text-muted-foreground mt-1">
                Any specific requirements, target segments, or special instructions.
              </p>
            </div>
            <Textarea
              id="notes"
              placeholder="e.g., Focus on enterprise accounts, avoid competitors in the XYZ space..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={loading}
              rows={4}
            />
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Onboarding: {client.name}</DialogTitle>
          <DialogDescription>
            Step {currentStep} of {STEPS.length}: {STEPS[currentStep - 1].description}
          </DialogDescription>
        </DialogHeader>

        {/* Progress Indicator */}
        <div className="py-4">
          <div className="flex items-center justify-between">
            {STEPS.map((step, index) => (
              <div key={step.id} className="flex items-center">
                {/* Step Circle */}
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all',
                    currentStep > step.id && 'bg-green-600 text-white',
                    currentStep === step.id && 'bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2',
                    currentStep < step.id && 'bg-muted text-muted-foreground'
                  )}
                >
                  {currentStep > step.id ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    step.id
                  )}
                </div>
                {/* Connector Line */}
                {index < STEPS.length - 1 && (
                  <div
                    className={cn(
                      'h-0.5 w-6 sm:w-10 mx-1',
                      currentStep > step.id ? 'bg-green-600' : 'bg-muted'
                    )}
                  />
                )}
              </div>
            ))}
          </div>
          {/* Step Labels (hidden on mobile) */}
          <div className="hidden sm:flex items-center justify-between mt-2">
            {STEPS.map((step) => (
              <div key={step.id} className="text-xs text-center w-8">
                <span
                  className={cn(
                    currentStep === step.id ? 'text-primary font-medium' : 'text-muted-foreground'
                  )}
                >
                  {step.title}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <div className="min-h-[200px] py-4">
          {renderStepContent()}
        </div>

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between pt-4 border-t">
          <Button
            type="button"
            variant="outline"
            onClick={handleBack}
            disabled={currentStep === 1 || loading}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            Back
          </Button>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>

            {currentStep < STEPS.length ? (
              <Button
                type="button"
                onClick={handleNext}
                disabled={!canProceed() || loading}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            ) : (
              <Button
                type="button"
                onClick={handleSubmit}
                disabled={!canProceed() || loading}
                className="bg-green-600 hover:bg-green-700"
              >
                {loading ? 'Saving...' : 'Complete Onboarding'}
                <Check className="h-4 w-4 ml-1" />
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
