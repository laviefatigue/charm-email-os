'use client';

import { useState, useMemo } from 'react';
import { ArrowRight, Check, AlertCircle } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
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
import { Card } from '@/components/ui/card';
import type { CSVColumnMapping, Lead } from '@/lib/types';
import { LEAD_FIELD_OPTIONS } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ColumnMappingStepProps {
  csvHeaders: string[];
  sampleData: Record<string, string>[]; // First 5 rows
  mappings: CSVColumnMapping[];
  onMappingsChange: (mappings: CSVColumnMapping[]) => void;
}

// Auto-suggest mappings based on common column names
const COLUMN_NAME_SUGGESTIONS: Record<string, keyof Lead | 'skip'> = {
  email: 'email',
  'e-mail': 'email',
  'email address': 'email',
  'first name': 'firstName',
  firstname: 'firstName',
  'first': 'firstName',
  'last name': 'lastName',
  lastname: 'lastName',
  'last': 'lastName',
  name: 'firstName', // Will need manual adjustment
  company: 'company',
  'company name': 'company',
  organization: 'company',
  title: 'title',
  'job title': 'title',
  position: 'title',
  role: 'title',
  linkedin: 'linkedInUrl',
  'linkedin url': 'linkedInUrl',
  'linkedin profile': 'linkedInUrl',
  phone: 'phone',
  'phone number': 'phone',
  mobile: 'phone',
  website: 'website',
  'company website': 'website',
  url: 'website',
  location: 'location',
  city: 'location',
  country: 'location',
  industry: 'industry',
  'company size': 'companySize',
  size: 'companySize',
  employees: 'companySize',
  notes: 'notes',
  comments: 'notes',
};

function suggestMapping(columnName: string): keyof Lead | 'custom' | 'skip' {
  const normalized = columnName.toLowerCase().trim();
  if (COLUMN_NAME_SUGGESTIONS[normalized]) {
    return COLUMN_NAME_SUGGESTIONS[normalized];
  }
  // If not found, default to skip
  return 'skip';
}

export function ColumnMappingStep({
  csvHeaders,
  sampleData,
  mappings,
  onMappingsChange,
}: ColumnMappingStepProps) {
  // Track custom field names separately
  const [customFieldNames, setCustomFieldNames] = useState<Record<string, string>>({});

  // Initialize mappings with suggestions if not already set
  useMemo(() => {
    if (mappings.length === 0 && csvHeaders.length > 0) {
      const initialMappings: CSVColumnMapping[] = csvHeaders.map((header) => ({
        csvColumn: header,
        leadField: suggestMapping(header),
      }));
      onMappingsChange(initialMappings);
    }
  }, [csvHeaders, mappings.length, onMappingsChange]);

  const handleMappingChange = (csvColumn: string, leadField: keyof Lead | 'custom' | 'skip') => {
    const updated = mappings.map((m) =>
      m.csvColumn === csvColumn
        ? {
            ...m,
            leadField,
            customFieldName: leadField === 'custom' ? customFieldNames[csvColumn] || '' : undefined,
          }
        : m
    );
    onMappingsChange(updated);
  };

  const handleCustomFieldNameChange = (csvColumn: string, name: string) => {
    setCustomFieldNames((prev) => ({ ...prev, [csvColumn]: name }));
    const updated = mappings.map((m) =>
      m.csvColumn === csvColumn
        ? { ...m, customFieldName: name }
        : m
    );
    onMappingsChange(updated);
  };

  // Validation: Check for required fields
  const hasEmail = mappings.some((m) => m.leadField === 'email');
  const hasFirstName = mappings.some((m) => m.leadField === 'firstName');

  // Count mapped fields (excluding skip)
  const mappedCount = mappings.filter((m) => m.leadField !== 'skip').length;

  return (
    <div className="space-y-6">
      {/* Validation Summary */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {hasEmail ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <AlertCircle className="h-4 w-4 text-red-500" />
              )}
              <span className={cn('text-sm', hasEmail ? 'text-green-600' : 'text-red-500')}>
                Email {hasEmail ? 'mapped' : 'required'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {hasFirstName ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <AlertCircle className="h-4 w-4 text-yellow-500" />
              )}
              <span className={cn('text-sm', hasFirstName ? 'text-green-600' : 'text-yellow-600')}>
                First Name {hasFirstName ? 'mapped' : '(recommended)'}
              </span>
            </div>
          </div>
          <Badge variant="secondary">
            {mappedCount} of {csvHeaders.length} columns mapped
          </Badge>
        </div>
      </Card>

      {/* Mapping Table */}
      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="w-[200px]">CSV Column</TableHead>
              <TableHead className="w-[50px]"></TableHead>
              <TableHead className="w-[200px]">Map To</TableHead>
              <TableHead>Sample Data</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mappings.map((mapping) => {
              const samples = sampleData.slice(0, 3).map((row) => row[mapping.csvColumn]);
              const isSkipped = mapping.leadField === 'skip';
              const isCustom = mapping.leadField === 'custom';

              return (
                <TableRow key={mapping.csvColumn} className={isSkipped ? 'opacity-50' : ''}>
                  <TableCell className="font-medium">
                    <code className="text-sm bg-muted px-2 py-1 rounded">{mapping.csvColumn}</code>
                  </TableCell>
                  <TableCell>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </TableCell>
                  <TableCell>
                    <div className="space-y-2">
                      <Select
                        value={mapping.leadField}
                        onValueChange={(v) =>
                          handleMappingChange(mapping.csvColumn, v as keyof Lead | 'custom' | 'skip')
                        }
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {LEAD_FIELD_OPTIONS.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {isCustom && (
                        <Input
                          placeholder="Custom field name"
                          value={customFieldNames[mapping.csvColumn] || mapping.customFieldName || ''}
                          onChange={(e) => handleCustomFieldNameChange(mapping.csvColumn, e.target.value)}
                          className="h-8 text-sm"
                        />
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {samples.filter(Boolean).map((sample, i) => (
                        <Badge key={i} variant="outline" className="text-xs font-normal max-w-[150px] truncate">
                          {sample}
                        </Badge>
                      ))}
                      {samples.filter(Boolean).length === 0 && (
                        <span className="text-xs text-muted-foreground italic">No data</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Preview Section */}
      <div>
        <Label className="text-sm font-semibold mb-3 block">Preview (First 5 rows)</Label>
        <div className="border rounded-lg overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead className="w-[50px]">#</TableHead>
                {mappings
                  .filter((m) => m.leadField !== 'skip')
                  .map((m) => (
                    <TableHead key={m.csvColumn} className="min-w-[120px]">
                      {m.leadField === 'custom' ? m.customFieldName || 'Custom' : LEAD_FIELD_OPTIONS.find((o) => o.value === m.leadField)?.label || m.leadField}
                    </TableHead>
                  ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sampleData.slice(0, 5).map((row, rowIndex) => (
                <TableRow key={rowIndex}>
                  <TableCell className="text-muted-foreground">{rowIndex + 1}</TableCell>
                  {mappings
                    .filter((m) => m.leadField !== 'skip')
                    .map((m) => (
                      <TableCell key={m.csvColumn} className="text-sm">
                        {row[m.csvColumn] || <span className="text-muted-foreground italic">—</span>}
                      </TableCell>
                    ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
