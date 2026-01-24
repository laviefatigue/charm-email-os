'use client';

import { useState, useEffect } from 'react';
import { Plus, Trash2, RefreshCw, Save, User, Star, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { Client, BaseName, SenderNameVariation, VariationPattern } from '@/lib/types';
import { clientApi } from '@/lib/api';

interface SenderNamesTabProps {
  clientId: string;
  client: Client;
  onSave?: () => void;
}

// Default patterns to use
const DEFAULT_PATTERNS = [
  'firstname.lastname',
  'f.lastname',
  'firstnamelastname',
  'firstname.l',
  'flastname',
];

export function SenderNamesTab({ clientId, client, onSave }: SenderNamesTabProps) {
  // State for base names (seeds)
  const [baseNames, setBaseNames] = useState<BaseName[]>([]);
  const [newFirstName, setNewFirstName] = useState('');
  const [newLastName, setNewLastName] = useState('');

  // State for patterns
  const [availablePatterns, setAvailablePatterns] = useState<VariationPattern[]>([]);
  const [selectedPatterns, setSelectedPatterns] = useState<string[]>(DEFAULT_PATTERNS);

  // State for variations
  const [variations, setVariations] = useState<SenderNameVariation[]>([]);
  const [approvedIndices, setApprovedIndices] = useState<Set<number>>(new Set());
  const [savedPrefixes, setSavedPrefixes] = useState<Set<string>>(new Set());
  const [variationCount, setVariationCount] = useState(10);

  // UI state
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Load existing configuration on mount
  useEffect(() => {
    loadConfig();
  }, [clientId]);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const config = await clientApi.getSenderNameConfig(clientId);
      setBaseNames(config.baseNames);
      setSelectedPatterns(config.patterns.length > 0 ? config.patterns : DEFAULT_PATTERNS);
      setVariations(config.variations);
      // All loaded variations are approved by default (they were saved)
      setApprovedIndices(new Set(config.variations.map((_, i) => i)));
      // Track which prefixes are already saved
      setSavedPrefixes(new Set(config.variations.map(v => v.emailPrefix)));
      setAvailablePatterns(config.availablePatterns);
      setHasUnsavedChanges(false);
    } catch (error) {
      console.error('Failed to load sender name config:', error);
      // Load just the patterns if config fails
      try {
        const patternsResponse = await clientApi.getNamePatterns();
        setAvailablePatterns(patternsResponse.patterns);
        setSelectedPatterns(patternsResponse.default_patterns);
      } catch {
        toast.error('Failed to load name patterns');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const addBaseName = () => {
    if (!newFirstName.trim() || !newLastName.trim()) {
      toast.error('Please enter both first and last name');
      return;
    }

    // Check for duplicate
    const exists = baseNames.some(
      bn => bn.firstName.toLowerCase() === newFirstName.toLowerCase() &&
            bn.lastName.toLowerCase() === newLastName.toLowerCase()
    );
    if (exists) {
      toast.error('This name already exists');
      return;
    }

    // First name is always founder
    const isFounder = baseNames.length === 0;
    setBaseNames([...baseNames, {
      firstName: newFirstName.trim(),
      lastName: newLastName.trim(),
      isFounder,
    }]);
    setNewFirstName('');
    setNewLastName('');
    setHasUnsavedChanges(true);
    setVariations([]); // Clear variations when base names change
  };

  const removeBaseName = (index: number) => {
    const newBaseNames = baseNames.filter((_, i) => i !== index);
    // If we removed the founder, make the first remaining name the founder
    if (newBaseNames.length > 0 && baseNames[index].isFounder) {
      newBaseNames[0].isFounder = true;
    }
    setBaseNames(newBaseNames);
    setHasUnsavedChanges(true);
    setVariations([]); // Clear variations when base names change
    setApprovedIndices(new Set());
  };

  const toggleFounder = (index: number) => {
    const newBaseNames = baseNames.map((bn, i) => ({
      ...bn,
      isFounder: i === index,
    }));
    setBaseNames(newBaseNames);
    setHasUnsavedChanges(true);
  };

  const togglePattern = (patternName: string) => {
    setSelectedPatterns(prev =>
      prev.includes(patternName)
        ? prev.filter(p => p !== patternName)
        : [...prev, patternName]
    );
    setHasUnsavedChanges(true);
    setVariations([]); // Clear variations when patterns change
    setApprovedIndices(new Set());
  };

  const generateVariations = async (append = false) => {
    if (baseNames.length === 0) {
      toast.error('Please add at least one base name');
      return;
    }

    if (selectedPatterns.length === 0) {
      toast.error('Please select at least one pattern');
      return;
    }

    setIsGenerating(true);
    try {
      const result = await clientApi.generateNameVariations(
        clientId,
        baseNames,
        selectedPatterns,
        variationCount
      );

      if (append && variations.length > 0) {
        // Get existing email prefixes to filter duplicates
        const existingPrefixes = new Set(variations.map(v => v.emailPrefix));
        const newVariations = result.variations.filter(v => !existingPrefixes.has(v.emailPrefix));

        if (newVariations.length === 0) {
          toast.info('No new unique variations could be generated. Try adding more base names or patterns.');
        } else {
          const startIndex = variations.length;
          setVariations([...variations, ...newVariations]);
          // Approve all new variations by default
          setApprovedIndices(prev => {
            const next = new Set(prev);
            newVariations.forEach((_, i) => next.add(startIndex + i));
            return next;
          });
          toast.success(`Added ${newVariations.length} new variations`);
        }
      } else {
        // Fresh generation - all approved by default
        setVariations(result.variations);
        setApprovedIndices(new Set(result.variations.map((_, i) => i)));
        toast.success(`Generated ${result.count} name variations`);
      }
      setHasUnsavedChanges(true);
    } catch (error) {
      console.error('Failed to generate variations:', error);
      toast.error('Failed to generate name variations');
    } finally {
      setIsGenerating(false);
    }
  };

  const toggleApproval = (index: number) => {
    setApprovedIndices(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
    setHasUnsavedChanges(true);
  };

  const approveAll = () => {
    setApprovedIndices(new Set(variations.map((_, i) => i)));
    setHasUnsavedChanges(true);
  };

  const clearAll = () => {
    setApprovedIndices(new Set());
    setHasUnsavedChanges(true);
  };

  const removeRejected = () => {
    const approvedVariations = variations.filter((_, i) => approvedIndices.has(i));
    setVariations(approvedVariations);
    setApprovedIndices(new Set(approvedVariations.map((_, i) => i)));
    setHasUnsavedChanges(true);
    toast.success(`Removed ${variations.length - approvedVariations.length} unapproved variations`);
  };

  const saveConfig = async () => {
    const approvedVariations = variations.filter((_, i) => approvedIndices.has(i));

    if (approvedVariations.length === 0) {
      toast.error('Please approve at least one variation to save');
      return;
    }

    setIsSaving(true);
    try {
      await clientApi.saveSenderNames(clientId, baseNames, approvedVariations, selectedPatterns);
      // Update state to only keep approved variations
      setVariations(approvedVariations);
      setApprovedIndices(new Set(approvedVariations.map((_, i) => i)));
      // Mark all approved variations as saved
      setSavedPrefixes(new Set(approvedVariations.map(v => v.emailPrefix)));
      setHasUnsavedChanges(false);
      toast.success(`Saved ${approvedVariations.length} sender names to client profile`);
      onSave?.();
    } catch (error) {
      console.error('Failed to save sender names:', error);
      toast.error('Failed to save sender names');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-[200px] w-full" />
        <Skeleton className="h-[150px] w-full" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Base Names Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Base Names (Seeds)
          </CardTitle>
          <CardDescription>
            Add the real identities for your client. The system will generate multiple email prefix variations from these names.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing base names */}
          {baseNames.length > 0 && (
            <div className="space-y-2">
              {baseNames.map((bn, index) => (
                <div
                  key={index}
                  className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg"
                >
                  <div className="flex-1 flex items-center gap-2">
                    <span className="font-medium">
                      {bn.firstName} {bn.lastName}
                    </span>
                    {bn.isFounder && (
                      <Badge variant="secondary" className="gap-1">
                        <Star className="h-3 w-3" />
                        Founder
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {!bn.isFounder && baseNames.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleFounder(index)}
                        title="Set as founder"
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeBaseName(index)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add new name form */}
          <div className="flex items-end gap-3">
            <div className="flex-1 space-y-2">
              <Label htmlFor="firstName">First Name</Label>
              <Input
                id="firstName"
                placeholder="Chris"
                value={newFirstName}
                onChange={(e) => setNewFirstName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addBaseName()}
              />
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="lastName">Last Name</Label>
              <Input
                id="lastName"
                placeholder="Booth"
                value={newLastName}
                onChange={(e) => setNewLastName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addBaseName()}
              />
            </div>
            <Button onClick={addBaseName} disabled={!newFirstName || !newLastName}>
              <Plus className="h-4 w-4 mr-2" />
              Add Name
            </Button>
          </div>

          {baseNames.length === 0 && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Add at least one base name to generate variations. The first name added will be marked as the founder.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Pattern Selection */}
      <Card>
        <CardHeader>
          <CardTitle>Variation Patterns</CardTitle>
          <CardDescription>
            Select which email prefix formats to generate. Each pattern creates a different format from your base names.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {availablePatterns.map((pattern) => (
              <div
                key={pattern.name}
                className="flex items-start space-x-3 p-3 rounded-lg border hover:bg-muted/50 cursor-pointer"
                onClick={() => togglePattern(pattern.name)}
              >
                <Checkbox
                  id={pattern.name}
                  checked={selectedPatterns.includes(pattern.name)}
                  onCheckedChange={() => togglePattern(pattern.name)}
                />
                <div className="space-y-1">
                  <Label htmlFor={pattern.name} className="cursor-pointer font-medium">
                    {pattern.example}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {pattern.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Generate button */}
          <div className="flex items-center gap-4 mt-6 pt-4 border-t">
            <div className="flex items-center gap-2">
              <Label htmlFor="count">Variations to generate:</Label>
              <Input
                id="count"
                type="number"
                min={1}
                max={10}
                value={variationCount}
                onChange={(e) => setVariationCount(Math.min(10, Math.max(1, parseInt(e.target.value) || 10)))}
                className="w-20"
              />
            </div>
            <Button
              onClick={() => generateVariations(false)}
              disabled={isGenerating || baseNames.length === 0 || selectedPatterns.length === 0}
            >
              {isGenerating ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Generate Variations
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Generated Variations Preview */}
      {variations.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>
                  Generated Variations ({approvedIndices.size} approved / {variations.length} total)
                </CardTitle>
                <CardDescription>
                  Check the variations you want to use. Only approved variations will be saved.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => generateVariations(true)}
                  disabled={isGenerating}
                >
                  {isGenerating ? (
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4 mr-2" />
                  )}
                  Generate More
                </Button>
                <Button
                  onClick={saveConfig}
                  disabled={isSaving || approvedIndices.size === 0}
                >
                  {isSaving ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      Save {approvedIndices.size} Names
                    </>
                  )}
                </Button>
              </div>
            </div>
            {/* Bulk actions */}
            <div className="flex items-center gap-2 pt-2">
              <Button variant="ghost" size="sm" onClick={approveAll}>
                Select All
              </Button>
              <Button variant="ghost" size="sm" onClick={clearAll}>
                Clear All
              </Button>
              {approvedIndices.size < variations.length && approvedIndices.size > 0 && (
                <Button variant="ghost" size="sm" onClick={removeRejected} className="text-destructive">
                  <Trash2 className="h-4 w-4 mr-1" />
                  Remove Unchecked
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={approvedIndices.size === variations.length}
                      onCheckedChange={(checked) => checked ? approveAll() : clearAll()}
                    />
                  </TableHead>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Email Prefix</TableHead>
                  <TableHead>Pattern</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {variations.map((v, index) => (
                  <TableRow
                    key={index}
                    className={!approvedIndices.has(index) ? 'opacity-50' : ''}
                  >
                    <TableCell>
                      <Checkbox
                        checked={approvedIndices.has(index)}
                        onCheckedChange={() => toggleApproval(index)}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{index + 1}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {v.baseName || `${v.firstName} ${v.lastName}`}
                        {v.isFounder && (
                          <Badge variant="secondary" className="gap-1">
                            <Star className="h-3 w-3" />
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="px-2 py-1 bg-muted rounded text-sm">
                        {v.emailPrefix}
                      </code>
                    </TableCell>
                    <TableCell>
                      {v.pattern && (
                        <code className="px-2 py-1 bg-muted rounded text-xs">
                          {v.pattern}
                        </code>
                      )}
                    </TableCell>
                    <TableCell>
                      {savedPrefixes.has(v.emailPrefix) ? (
                        <Badge variant="default" className="gap-1 bg-green-600 hover:bg-green-600">
                          <CheckCircle2 className="h-3 w-3" />
                          Saved
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="gap-1 text-muted-foreground">
                          New
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {approvedIndices.size === 0 && (
              <Alert className="mt-4" variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No variations selected. Check at least one variation to save.
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
