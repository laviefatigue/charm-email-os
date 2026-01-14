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
import { useClientStore } from '@/lib/stores';

interface ClientFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (clientId: string) => void;
}

export function ClientForm({ open, onOpenChange, onSuccess }: ClientFormProps) {
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(false);

  const { addClient } = useClientStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim() || !domain.trim()) {
      toast.error('Please fill in all fields');
      return;
    }

    setLoading(true);

    // Simulate a small delay
    await new Promise((resolve) => setTimeout(resolve, 300));

    const client = await addClient({ name: name.trim(), domain: domain.trim() });
    toast.success('Client created successfully');

    setName('');
    setDomain('');
    setLoading(false);
    onOpenChange(false);

    if (onSuccess) {
      onSuccess(client.id);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add New Client</DialogTitle>
            <DialogDescription>
              Create a new client to start managing their email campaigns.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Client Name</Label>
              <Input
                id="name"
                placeholder="e.g., Acme Corp"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={loading}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="domain">Primary Domain</Label>
              <Input
                id="domain"
                placeholder="e.g., acme.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={loading}
              />
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
              {loading ? 'Creating...' : 'Create Client'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
