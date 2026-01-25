'use client';

import { useState, useEffect } from 'react';
import { Save, User, RefreshCw, CheckCircle2, Mail } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { Client } from '@/lib/types';
import { clientApi } from '@/lib/api';

interface SenderNamesTabProps {
  clientId: string;
  client: Client;
  onSave?: () => void;
}

export function SenderNamesTab({ clientId, client, onSave }: SenderNamesTabProps) {
  // Form state
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [provider, setProvider] = useState<'entra' | 'google'>('entra');

  // Saved state
  const [savedName, setSavedName] = useState<{ firstName: string; lastName: string } | null>(null);
  const [savedPrefixes, setSavedPrefixes] = useState<string[]>([]);
  const [savedProvider, setSavedProvider] = useState<string>('');

  // UI state
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Load existing configuration on mount
  useEffect(() => {
    loadConfig();
  }, [clientId]);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const config = await clientApi.getSenderNameConfig(clientId);

      if (config.hasConfig && config.baseNames.length > 0) {
        const baseName = config.baseNames[0];
        setSavedName({
          firstName: baseName.firstName,
          lastName: baseName.lastName,
        });
        setFirstName(baseName.firstName);
        setLastName(baseName.lastName);

        // Get saved prefixes
        const prefixes = config.variations.map(v => v.emailPrefix);
        setSavedPrefixes(prefixes);

        // Get provider from saved config
        const savedProv = (config as any).provider || 'entra';
        setSavedProvider(savedProv);
        setProvider(savedProv as 'entra' | 'google');
      }
    } catch (error) {
      console.error('Failed to load sender name config:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!firstName.trim() || !lastName.trim()) {
      toast.error('Please enter both first and last name');
      return;
    }

    setIsSaving(true);
    try {
      const result = await clientApi.setSenderName(
        clientId,
        firstName.trim(),
        lastName.trim(),
        provider
      );

      setSavedName({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
      });
      setSavedPrefixes(result.prefixes);
      setSavedProvider(result.provider);

      toast.success(`Generated ${result.prefixCount} email prefixes for ${firstName} ${lastName}`);
      onSave?.();
    } catch (error) {
      console.error('Failed to save sender name:', error);
      toast.error('Failed to save sender name');
    } finally {
      setIsSaving(false);
    }
  };

  const hasChanges = savedName
    ? firstName !== savedName.firstName || lastName !== savedName.lastName || provider !== savedProvider
    : firstName.trim() !== '' || lastName.trim() !== '';

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-[200px] w-full" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Sender Name Setup */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Sender Name
          </CardTitle>
          <CardDescription>
            Enter the sender name for this client. The system will automatically generate all email prefix variations.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Name input */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="firstName">First Name</Label>
              <Input
                id="firstName"
                placeholder="Chris"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lastName">Last Name</Label>
              <Input
                id="lastName"
                placeholder="Booth"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
              />
            </div>
          </div>

          {/* Provider selection */}
          <div className="space-y-2">
            <Label htmlFor="provider">Infrastructure Provider</Label>
            <Select value={provider} onValueChange={(v) => setProvider(v as 'entra' | 'google')}>
              <SelectTrigger className="w-[280px]">
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="entra">
                  <div className="flex items-center gap-2">
                    <span>Microsoft Entra</span>
                    <Badge variant="secondary" className="ml-2">52 prefixes</Badge>
                  </div>
                </SelectItem>
                <SelectItem value="google">
                  <div className="flex items-center gap-2">
                    <span>Google Workspace</span>
                    <Badge variant="secondary" className="ml-2">10 prefixes</Badge>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">
              {provider === 'entra'
                ? 'Microsoft Entra: Generates 52 unique email prefixes per name'
                : 'Google Workspace: Generates 10 unique email prefixes per name'}
            </p>
          </div>

          {/* Save button */}
          <Button
            onClick={handleSave}
            disabled={isSaving || !firstName.trim() || !lastName.trim()}
            className="w-full md:w-auto"
          >
            {isSaving ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Generating Prefixes...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {savedName ? 'Update & Regenerate Prefixes' : 'Generate Email Prefixes'}
              </>
            )}
          </Button>

          {/* Saved indicator */}
          {savedName && !hasChanges && (
            <div className="flex items-center gap-2 text-green-600">
              <CheckCircle2 className="h-4 w-4" />
              <span className="text-sm">
                Saved: {savedName.firstName} {savedName.lastName} ({savedPrefixes.length} prefixes)
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Generated Prefixes Preview */}
      {savedPrefixes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Generated Email Prefixes ({savedPrefixes.length})
            </CardTitle>
            <CardDescription>
              These prefixes will be used when creating inboxes: prefix@domain.com
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="max-h-[400px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Email Prefix</TableHead>
                    <TableHead>Example Email</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {savedPrefixes.map((prefix, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium text-muted-foreground">{index + 1}</TableCell>
                      <TableCell>
                        <code className="px-2 py-1 bg-muted rounded text-sm">
                          {prefix}
                        </code>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {prefix}@example.com
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
