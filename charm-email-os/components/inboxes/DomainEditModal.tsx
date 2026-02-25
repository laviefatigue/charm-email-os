'use client';

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Globe, Sparkles } from 'lucide-react';
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
import { Card } from '@/components/ui/card';
import { useInfrastructureStore } from '@/lib/stores';
import type { Domain } from '@/lib/types';

interface DomainEditModalProps {
  domain: Domain | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// AI suggestion samples for domains
const AI_SUGGESTIONS = [
  'Consider using a shorter prefix for better memorability.',
  'Domains with "mail" or "go" prefixes tend to have higher deliverability.',
  'Try a variation that matches your brand voice.',
  'Shorter domains are easier for recipients to trust.',
];

export function DomainEditModal({ domain, open, onOpenChange }: DomainEditModalProps) {
  const [domainValue, setDomainValue] = useState('');
  const [loading, setLoading] = useState(false);

  const { updateDomain, resetDomainStatus } = useInfrastructureStore();

  // Get a stable AI suggestion
  const aiSuggestion = AI_SUGGESTIONS[0];

  useEffect(() => {
    if (domain) {
      setDomainValue(domain.domain);
    }
  }, [domain]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!domain) return;

    if (!domainValue.trim()) {
      toast.error('Please enter a domain');
      return;
    }

    // Basic domain validation
    const domainRegex = /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$/;
    if (!domainRegex.test(domainValue.trim())) {
      toast.error('Please enter a valid domain (e.g., mail-company.com)');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    updateDomain(domain.id, { domain: domainValue.trim() });
    resetDomainStatus(domain.id);

    toast.success('Domain updated and ready for approval');

    setLoading(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit Domain</DialogTitle>
            <DialogDescription>
              Modify this domain before resubmitting for approval.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* AI Suggestion Card */}
            <Card className="p-4 bg-primary/5 border-primary/20">
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <Sparkles className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">Suggestion</p>
                  <p className="text-sm text-muted-foreground mt-1">{aiSuggestion}</p>
                </div>
              </div>
            </Card>

            {/* Domain Input */}
            <div className="grid gap-2">
              <Label htmlFor="domain">Domain Name</Label>
              <div className="relative">
                <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="domain"
                  placeholder="e.g., mail-company.com"
                  value={domainValue}
                  onChange={(e) => setDomainValue(e.target.value)}
                  disabled={loading}
                  className="pl-9"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Enter the full domain name including TLD
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Saving...' : 'Save & Resubmit'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
