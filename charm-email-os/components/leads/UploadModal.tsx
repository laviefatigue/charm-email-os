'use client';

import { useState, useCallback } from 'react';
import { Upload, FileSpreadsheet, X, Check, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ColumnMappingStep } from './ColumnMappingStep';
import type { CSVColumnMapping, Lead } from '@/lib/types';
import { cn } from '@/lib/utils';

interface UploadModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (count: number) => void;
  campaignName: string;
}

type UploadState = 'idle' | 'mapping' | 'uploading' | 'complete';

// Simple CSV parser
function parseCSV(csvText: string): { headers: string[]; rows: Record<string, string>[] } {
  const lines = csvText.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length === 0) return { headers: [], rows: [] };

  // Parse header row
  const headers = parseCSVLine(lines[0]);

  // Parse data rows
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    const row: Record<string, string> = {};
    headers.forEach((header, index) => {
      row[header] = values[index] || '';
    });
    rows.push(row);
  }

  return { headers, rows };
}

// Parse a single CSV line, handling quoted values
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++; // Skip escaped quote
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());

  return result;
}

export function UploadModal({ open, onOpenChange, onUpload, campaignName }: UploadModalProps) {
  const [state, setState] = useState<UploadState>('idle');
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  // CSV data state
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvData, setCsvData] = useState<Record<string, string>[]>([]);
  const [columnMappings, setColumnMappings] = useState<CSVColumnMapping[]>([]);

  const processFile = useCallback(async (file: File) => {
    setFileName(file.name);

    try {
      const text = await file.text();
      const { headers, rows } = parseCSV(text);

      if (headers.length === 0) {
        toast.error('CSV file appears to be empty');
        return;
      }

      setCsvHeaders(headers);
      setCsvData(rows);
      setColumnMappings([]); // Will be initialized by ColumnMappingStep
      setState('mapping');
    } catch {
      toast.error('Failed to parse CSV file');
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.csv')) {
        processFile(file);
      } else {
        toast.error('Please upload a CSV file');
      }
    },
    [processFile]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        processFile(file);
      }
    },
    [processFile]
  );

  // Check if required fields are mapped
  const hasRequiredMappings = columnMappings.some((m) => m.leadField === 'email');

  const handleUpload = async () => {
    if (!hasRequiredMappings) {
      toast.error('Please map at least the Email column');
      return;
    }

    setState('uploading');
    setProgress(0);

    // Simulate upload progress (in real app, this would be actual API calls)
    for (let i = 0; i <= 100; i += 10) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      setProgress(i);
    }

    const leadCount = csvData.length;
    setState('complete');
    onUpload(leadCount);
    toast.success(`${leadCount} leads uploaded successfully!`);

    // Reset after delay
    setTimeout(() => {
      onOpenChange(false);
      resetState();
    }, 1500);
  };

  const resetState = () => {
    setState('idle');
    setFileName(null);
    setProgress(0);
    setCsvHeaders([]);
    setCsvData([]);
    setColumnMappings([]);
  };

  const handleCancel = () => {
    resetState();
  };

  const handleBack = () => {
    setState('idle');
    setFileName(null);
    setCsvHeaders([]);
    setCsvData([]);
    setColumnMappings([]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('transition-all', state === 'mapping' ? 'sm:max-w-4xl' : 'sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>
            {state === 'idle' && 'Upload Leads'}
            {state === 'mapping' && 'Map CSV Columns'}
            {state === 'uploading' && 'Uploading Leads'}
            {state === 'complete' && 'Upload Complete'}
          </DialogTitle>
          <DialogDescription>
            {state === 'idle' && `Upload a CSV file to add leads to "${campaignName}"`}
            {state === 'mapping' && `Map CSV columns to lead fields • ${csvData.length} rows detected`}
            {state === 'uploading' && 'Processing your leads...'}
            {state === 'complete' && 'All leads have been imported'}
          </DialogDescription>
        </DialogHeader>

        {state === 'idle' && (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              'border-2 border-dashed rounded-lg p-8 text-center transition-colors',
              isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/50'
            )}
          >
            <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-4" />
            <p className="text-sm font-medium mb-1">Drag and drop your CSV file here</p>
            <p className="text-xs text-muted-foreground mb-4">or click to browse</p>
            <input type="file" accept=".csv" onChange={handleFileInput} className="hidden" id="file-upload" />
            <label htmlFor="file-upload">
              <Button variant="outline" size="sm" className="cursor-pointer" asChild>
                <span>Browse Files</span>
              </Button>
            </label>
          </div>
        )}

        {state === 'mapping' && (
          <div className="space-y-4">
            {/* File Info */}
            <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
              <FileSpreadsheet className="h-8 w-8 text-primary" />
              <div className="flex-1">
                <p className="font-medium text-sm">{fileName}</p>
                <p className="text-xs text-muted-foreground">{csvData.length} leads detected</p>
              </div>
              <Button variant="ghost" size="icon" onClick={handleCancel}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Column Mapping */}
            <div className="max-h-[50vh] overflow-y-auto">
              <ColumnMappingStep
                csvHeaders={csvHeaders}
                sampleData={csvData.slice(0, 5)}
                mappings={columnMappings}
                onMappingsChange={setColumnMappings}
              />
            </div>

            {/* Validation Warning */}
            {!hasRequiredMappings && (
              <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <p>Email field is required. Please map a column to Email.</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-between pt-2">
              <Button variant="outline" onClick={handleBack}>
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
              <Button onClick={handleUpload} disabled={!hasRequiredMappings}>
                Upload {csvData.length} Leads
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}

        {state === 'uploading' && (
          <div className="py-8 space-y-4">
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
            </div>
            <p className="text-center text-sm text-muted-foreground">Uploading {csvData.length} leads...</p>
            <Progress value={progress} className="h-2" />
          </div>
        )}

        {state === 'complete' && (
          <div className="py-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-100 mx-auto mb-4">
              <Check className="h-6 w-6 text-green-600" />
            </div>
            <p className="font-medium">Upload Complete!</p>
            <p className="text-sm text-muted-foreground">{csvData.length} leads added to campaign</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
