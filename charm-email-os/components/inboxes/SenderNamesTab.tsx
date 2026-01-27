'use client';

import { useState, useEffect, useCallback } from 'react';
import { Plus, User, RefreshCw, CheckCircle2, Mail, Trash2, Crown, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import type { Client } from '@/lib/types';
import { clientApi } from '@/lib/api';

interface SenderName {
  id: string;
  firstName: string;
  lastName: string;
  isFounder: boolean;
  prefixes: string[];
  createdAt?: string;
}

interface SenderNamesTabProps {
  clientId: string;
  client: Client;
  onSave?: () => void;
}

export function SenderNamesTab({ clientId, client, onSave }: SenderNamesTabProps) {
  // Form state for adding new names
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isFounder, setIsFounder] = useState(false);
  const [provider, setProvider] = useState<'entra' | 'google'>('entra');

  // Saved state - now supports multiple names
  const [senderNames, setSenderNames] = useState<SenderName[]>([]);
  const [savedProvider, setSavedProvider] = useState<string>('entra');

  // UI state
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [expandedItems, setExpandedItems] = useState<string[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Load existing configuration on mount
  useEffect(() => {
    loadConfig();
  }, [clientId]);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const config = await clientApi.getSenderNameConfig(clientId);

      if (config.hasConfig && config.baseNames.length > 0) {
        // Convert API response to SenderName format
        // Group variations by base name
        const namesMap = new Map<string, SenderName>();

        config.baseNames.forEach((baseName: any, index: number) => {
          const key = `${baseName.firstName}-${baseName.lastName}`.toLowerCase();
          if (!namesMap.has(key)) {
            namesMap.set(key, {
              id: `name-${index}`,
              firstName: baseName.firstName,
              lastName: baseName.lastName,
              isFounder: baseName.isFounder || index === 0,
              prefixes: [],
              createdAt: baseName.createdAt,
            });
          }
        });

        // Assign prefixes to the first (and likely only) name
        if (namesMap.size > 0) {
          const keysIterator = namesMap.keys().next();
          if (!keysIterator.done && keysIterator.value) {
            const firstSenderName = namesMap.get(keysIterator.value);
            if (firstSenderName) {
              firstSenderName.prefixes = config.variations.map((v: any) => v.emailPrefix);
            }
          }
        }

        setSenderNames(Array.from(namesMap.values()));

        // Get provider from saved config
        const savedProv = (config as any).provider || 'entra';
        setSavedProvider(savedProv);
        setProvider(savedProv as 'entra' | 'google');

        // Auto-expand the first name
        if (namesMap.size > 0) {
          setExpandedItems(['name-0']);
        }
      }
    } catch (error) {
      console.error('Failed to load sender name config:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddName = async () => {
    if (!firstName.trim() || !lastName.trim()) {
      toast.error('Please enter both first and last name');
      return;
    }

    // Check for duplicates
    const exists = senderNames.some(
      (n) =>
        n.firstName.toLowerCase() === firstName.trim().toLowerCase() &&
        n.lastName.toLowerCase() === lastName.trim().toLowerCase()
    );
    if (exists) {
      toast.error('This name already exists');
      return;
    }

    setIsAdding(true);
    try {
      // If this is the first name or marked as founder, use setSenderName
      // Otherwise, we need to regenerate all names together
      const result = await clientApi.setSenderName(
        clientId,
        firstName.trim(),
        lastName.trim(),
        provider
      );

      const newName: SenderName = {
        id: `name-${senderNames.length}`,
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        isFounder: senderNames.length === 0 || isFounder,
        prefixes: result.prefixes,
        createdAt: new Date().toISOString(),
      };

      // For now, replace existing names (single name support)
      // TODO: Backend support for multiple names
      setSenderNames([newName]);
      setSavedProvider(result.provider);
      setExpandedItems([newName.id]);

      // Reset form
      setFirstName('');
      setLastName('');
      setIsFounder(false);

      toast.success(`Generated ${result.prefixCount} email prefixes for ${newName.firstName} ${newName.lastName}`);
      onSave?.();
    } catch (error) {
      console.error('Failed to add sender name:', error);
      toast.error('Failed to add sender name');
    } finally {
      setIsAdding(false);
    }
  };

  const handleDeleteName = useCallback(async (nameId: string) => {
    setDeletingId(nameId);
    try {
      // For now, just remove from local state
      // TODO: Backend support for deleting specific names
      setSenderNames((prev) => prev.filter((n) => n.id !== nameId));
      setExpandedItems((prev) => prev.filter((id) => id !== nameId));
      toast.success('Sender name removed');
    } catch (error) {
      console.error('Failed to delete sender name:', error);
      toast.error('Failed to delete sender name');
    } finally {
      setDeletingId(null);
    }
  }, []);

  const handleRegeneratePrefixes = useCallback(async (name: SenderName) => {
    try {
      const result = await clientApi.setSenderName(
        clientId,
        name.firstName,
        name.lastName,
        provider
      );

      setSenderNames((prev) =>
        prev.map((n) =>
          n.id === name.id ? { ...n, prefixes: result.prefixes } : n
        )
      );

      toast.success(`Regenerated ${result.prefixCount} prefixes for ${name.firstName} ${name.lastName}`);
    } catch (error) {
      console.error('Failed to regenerate prefixes:', error);
      toast.error('Failed to regenerate prefixes');
    }
  }, [clientId, provider]);

  const totalPrefixes = senderNames.reduce((sum, n) => sum + n.prefixes.length, 0);

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
      {/* Sender Names List with Accordion */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Sender Names
              </CardTitle>
              <CardDescription>
                Each name generates 52 unique email prefix variations for inbox creation
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-sm">
                {senderNames.length} {senderNames.length === 1 ? 'name' : 'names'}
              </Badge>
              <Badge variant="outline" className="text-sm">
                {totalPrefixes} total prefixes
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Names Accordion */}
          {senderNames.length > 0 ? (
            <Accordion
              type="multiple"
              value={expandedItems}
              onValueChange={setExpandedItems}
              className="space-y-2"
            >
              {senderNames.map((name) => (
                <AccordionItem
                  key={name.id}
                  value={name.id}
                  className="border rounded-lg px-4"
                >
                  <AccordionTrigger className="hover:no-underline">
                    <div className="flex items-center justify-between w-full pr-4">
                      <div className="flex items-center gap-3">
                        <User className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">
                          {name.firstName} {name.lastName}
                        </span>
                        {name.isFounder && (
                          <Badge variant="default" className="text-xs bg-amber-500 hover:bg-amber-600">
                            <Crown className="h-3 w-3 mr-1" />
                            Founder
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">
                          {name.prefixes.length} prefixes
                        </Badge>
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="pt-2 pb-4 space-y-4">
                      {/* Action buttons */}
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleRegeneratePrefixes(name)}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" />
                          Regenerate
                        </Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              disabled={deletingId === name.id}
                            >
                              <Trash2 className="h-3 w-3 mr-1" />
                              Remove
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Remove Sender Name?</AlertDialogTitle>
                              <AlertDialogDescription>
                                This will remove {name.firstName} {name.lastName} and all {name.prefixes.length} email prefixes.
                                This action cannot be undone.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => handleDeleteName(name.id)}
                                className="bg-destructive hover:bg-destructive/90"
                              >
                                Remove
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>

                      {/* Prefixes table */}
                      <div className="max-h-[300px] overflow-auto border rounded-md">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="w-12">#</TableHead>
                              <TableHead>Email Prefix</TableHead>
                              <TableHead>Example Email</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {name.prefixes.map((prefix, index) => (
                              <TableRow key={index}>
                                <TableCell className="font-medium text-muted-foreground">
                                  {index + 1}
                                </TableCell>
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
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <User className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p>No sender names configured yet.</p>
              <p className="text-sm">Add a name below to generate email prefixes.</p>
            </div>
          )}

          {/* Add New Name Form */}
          <div className="border-t pt-6">
            <h4 className="text-sm font-medium mb-4 flex items-center gap-2">
              <Plus className="h-4 w-4" />
              {senderNames.length === 0 ? 'Add Founder Name' : 'Add Team Member'}
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div className="space-y-2">
                <Label htmlFor="firstName">First Name</Label>
                <Input
                  id="firstName"
                  placeholder="Chris"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddName()}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input
                  id="lastName"
                  placeholder="Booth"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddName()}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground text-xs">Role</Label>
                <Badge
                  variant={senderNames.length === 0 ? 'default' : 'secondary'}
                  className="h-9 px-3 flex items-center justify-center cursor-default"
                >
                  {senderNames.length === 0 ? (
                    <>
                      <Crown className="h-3 w-3 mr-1" />
                      Founder
                    </>
                  ) : (
                    <>
                      <Users className="h-3 w-3 mr-1" />
                      Team Member
                    </>
                  )}
                </Badge>
              </div>
              <Button
                onClick={handleAddName}
                disabled={isAdding || !firstName.trim() || !lastName.trim()}
              >
                {isAdding ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4 mr-2" />
                    Add & Generate
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary Card */}
      {senderNames.length > 0 && (
        <Card className="bg-muted/30">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <Mail className="h-8 w-8 text-primary" />
                <div>
                  <p className="text-lg font-semibold">
                    {totalPrefixes} Email Prefixes Ready
                  </p>
                  <p className="text-sm text-muted-foreground">
                    From {senderNames.length} sender {senderNames.length === 1 ? 'name' : 'names'} using {provider === 'entra' ? 'Microsoft Entra' : 'Google Workspace'}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Prefixes per domain</p>
                <p className="text-2xl font-bold text-primary">{totalPrefixes}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
