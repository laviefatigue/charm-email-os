'use client';

import { useState } from 'react';
import { toast } from 'sonner';
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
import { useInfrastructureStore } from '@/lib/stores';

interface DomainFormProps {
  clientId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DomainForm({ clientId, open, onOpenChange }: DomainFormProps) {
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(false);

  const { addDomain } = useInfrastructureStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!domain.trim()) {
      toast.error('Please enter a domain name');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    addDomain({ clientId, domain: domain.trim() });
    toast.success('Domain purchase request submitted for approval');

    setDomain('');
    setLoading(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Purchase Domain</DialogTitle>
            <DialogDescription>
              Request a new domain for email sending. Domains require approval before purchasing.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="domain">Domain Name</Label>
              <Input
                id="domain"
                placeholder="e.g., outreach-emails.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={loading}
              />
            </div>

            <div className="p-3 bg-muted rounded-lg">
              <p className="text-sm font-medium">Estimated Cost</p>
              <p className="text-2xl font-bold">$12<span className="text-sm font-normal text-muted-foreground">/year</span></p>
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
              {loading ? 'Submitting...' : 'Request Domain'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
