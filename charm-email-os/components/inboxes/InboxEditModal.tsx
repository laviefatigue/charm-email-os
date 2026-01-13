'use client';

import { useState, useEffect, useMemo } from 'react';
import { toast } from 'sonner';
import { Mail, Sparkles, User } from 'lucide-react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useInfrastructureStore } from '@/lib/stores';
import type { Inbox, Domain } from '@/lib/types';

interface InboxEditModalProps {
  inbox: Inbox | null;
  domains: Domain[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// AI suggestion samples for inboxes
const AI_SUGGESTIONS = [
  'First names work better than initials for cold outreach.',
  'Consider using common name variations for better trust.',
  'Match the email format to your target industry norms.',
  'Shorter email addresses tend to appear more authentic.',
];

export function InboxEditModal({ inbox, domains, open, onOpenChange }: InboxEditModalProps) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [selectedDomainId, setSelectedDomainId] = useState('');
  const [loading, setLoading] = useState(false);

  const { updateInbox, resetInboxStatus } = useInfrastructureStore();

  // Filter to only approved domains
  const approvedDomains = useMemo(
    () => domains.filter((d) => d.status === 'approved' || d.status === 'active' || d.status === 'warming'),
    [domains]
  );

  // Get a stable AI suggestion
  const aiSuggestion = AI_SUGGESTIONS[0];

  useEffect(() => {
    if (inbox) {
      setFirstName(inbox.firstName);
      setLastName(inbox.lastName);
      setSelectedDomainId(inbox.domainId);
    }
  }, [inbox]);

  // Compute email preview
  const emailPreview = useMemo(() => {
    if (!firstName || !lastName || !selectedDomainId) return '';
    const domain = domains.find((d) => d.id === selectedDomainId);
    if (!domain) return '';
    return `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${domain.domain}`;
  }, [firstName, lastName, selectedDomainId, domains]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inbox) return;

    if (!firstName.trim() || !lastName.trim()) {
      toast.error('Please enter first and last name');
      return;
    }

    if (!selectedDomainId) {
      toast.error('Please select a domain');
      return;
    }

    const domain = domains.find((d) => d.id === selectedDomainId);
    if (!domain) {
      toast.error('Invalid domain selected');
      return;
    }

    setLoading(true);

    await new Promise((resolve) => setTimeout(resolve, 500));

    const newEmail = `${firstName.toLowerCase().trim()}.${lastName.toLowerCase().trim()}@${domain.domain}`;

    updateInbox(inbox.id, {
      firstName: firstName.trim(),
      lastName: lastName.trim(),
      domainId: selectedDomainId,
      email: newEmail,
    });
    resetInboxStatus(inbox.id);

    toast.success('Inbox updated and ready for approval');

    setLoading(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit Inbox</DialogTitle>
            <DialogDescription>
              Modify this inbox before resubmitting for approval.
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

            {/* Name Fields */}
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="firstName">First Name</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="firstName"
                    placeholder="e.g., John"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    disabled={loading}
                    className="pl-9"
                  />
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input
                  id="lastName"
                  placeholder="e.g., Smith"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  disabled={loading}
                />
              </div>
            </div>

            {/* Domain Select */}
            <div className="grid gap-2">
              <Label htmlFor="domain">Domain</Label>
              <Select
                value={selectedDomainId}
                onValueChange={setSelectedDomainId}
                disabled={loading || approvedDomains.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select an approved domain" />
                </SelectTrigger>
                <SelectContent>
                  {approvedDomains.map((domain) => (
                    <SelectItem key={domain.id} value={domain.id}>
                      {domain.domain}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {approvedDomains.length === 0 && (
                <p className="text-xs text-destructive">
                  No approved domains available. Please approve a domain first.
                </p>
              )}
            </div>

            {/* Email Preview */}
            {emailPreview && (
              <div className="grid gap-2">
                <Label>Email Preview</Label>
                <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-mono">{emailPreview}</span>
                </div>
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
            <Button type="submit" disabled={loading || approvedDomains.length === 0}>
              {loading ? 'Saving...' : 'Save & Resubmit'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
