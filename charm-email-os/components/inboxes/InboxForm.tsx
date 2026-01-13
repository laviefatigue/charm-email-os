'use client';

import { useState, useMemo } from 'react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useInfrastructureStore } from '@/lib/stores';

interface InboxFormProps {
  clientId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InboxForm({ clientId, open, onOpenChange }: InboxFormProps) {
  const [selectedDomainId, setSelectedDomainId] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [loading, setLoading] = useState(false);

  const { getDomainsByClient, domains, addInbox } = useInfrastructureStore();

  const clientDomains = useMemo(() => {
    return getDomainsByClient(clientId).filter(
      (d) => d.status === 'active' || d.status === 'approved' || d.status === 'warming'
    );
  }, [getDomainsByClient, clientId]);

  const selectedDomain = domains.find((d) => d.id === selectedDomainId);

  const generatedEmail = useMemo(() => {
    if (!firstName.trim() || !selectedDomain) return '';
    return `${firstName.toLowerCase().trim()}@${selectedDomain.domain}`;
  }, [firstName, selectedDomain]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedDomainId || !firstName.trim() || !lastName.trim()) {
      toast.error('Please fill in all fields');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    addInbox({
      clientId,
      domainId: selectedDomainId,
      firstName: firstName.trim(),
      lastName: lastName.trim(),
      email: generatedEmail,
    });

    toast.success('Inbox request submitted for approval');

    setSelectedDomainId('');
    setFirstName('');
    setLastName('');
    setLoading(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Purchase Inbox</DialogTitle>
            <DialogDescription>
              Create a new email inbox for sending campaigns. Inboxes require approval.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="domain">Domain</Label>
              <Select value={selectedDomainId} onValueChange={setSelectedDomainId} disabled={loading}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a domain" />
                </SelectTrigger>
                <SelectContent>
                  {clientDomains.map((domain) => (
                    <SelectItem key={domain.id} value={domain.id}>
                      {domain.domain}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {clientDomains.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No active domains available. Purchase a domain first.
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="firstName">First Name</Label>
                <Input
                  id="firstName"
                  placeholder="Sarah"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  disabled={loading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input
                  id="lastName"
                  placeholder="Chen"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>

            {generatedEmail && (
              <div className="p-3 bg-muted rounded-lg">
                <p className="text-sm font-medium">Generated Email</p>
                <p className="text-lg font-mono">{generatedEmail}</p>
              </div>
            )}
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
            <Button type="submit" disabled={loading || clientDomains.length === 0}>
              {loading ? 'Submitting...' : 'Request Inbox'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
