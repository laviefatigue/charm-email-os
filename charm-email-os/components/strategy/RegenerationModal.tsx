'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ScopeOption {
  value: string;
  label: string;
  description?: string;
}

export interface RegenerationModalConfig {
  title: string;
  description: string;
  placeholder: string;
  currentContent?: string;
  scopeOptions?: ScopeOption[];
  showPreserveOption?: boolean;
  preserveLabel?: string;
}

interface RegenerationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (instruction: string, scope?: string, preserveExisting?: boolean) => Promise<void>;
  config: RegenerationModalConfig;
  isSubmitting?: boolean;
}

export function RegenerationModal({
  isOpen,
  onClose,
  onSubmit,
  config,
  isSubmitting = false,
}: RegenerationModalProps) {
  const [instruction, setInstruction] = useState('');
  const [selectedScope, setSelectedScope] = useState<string>(
    config.scopeOptions?.[0]?.value || ''
  );
  const [preserveExisting, setPreserveExisting] = useState(false);
  const [showCurrentContent, setShowCurrentContent] = useState(false);

  const handleSubmit = async () => {
    await onSubmit(
      instruction,
      config.scopeOptions ? selectedScope : undefined,
      config.showPreserveOption ? preserveExisting : undefined
    );
    // Reset state on success
    setInstruction('');
    setPreserveExisting(false);
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setInstruction('');
      setPreserveExisting(false);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            {config.title}
          </DialogTitle>
          <DialogDescription>{config.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Current Content Preview (collapsible) */}
          {config.currentContent && (
            <div className="border rounded-lg overflow-hidden">
              <button
                type="button"
                className="w-full flex items-center justify-between p-3 text-sm bg-muted/50 hover:bg-muted transition-colors"
                onClick={() => setShowCurrentContent(!showCurrentContent)}
              >
                <span className="font-medium text-muted-foreground">
                  Current Content
                </span>
                {showCurrentContent ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>
              {showCurrentContent && (
                <div className="p-3 text-sm text-muted-foreground bg-muted/30 max-h-32 overflow-y-auto whitespace-pre-wrap">
                  {config.currentContent}
                </div>
              )}
            </div>
          )}

          {/* Scope Selection (if applicable) */}
          {config.scopeOptions && config.scopeOptions.length > 0 && (
            <div>
              <Label className="mb-2 block">Revision scope:</Label>
              <div className="space-y-2">
                {config.scopeOptions.map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                      selectedScope === option.value
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50'
                    )}
                  >
                    <input
                      type="radio"
                      name="scope"
                      value={option.value}
                      checked={selectedScope === option.value}
                      onChange={() => setSelectedScope(option.value)}
                      className="mt-0.5"
                    />
                    <div>
                      <span className="text-sm font-medium">{option.label}</span>
                      {option.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {option.description}
                        </p>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Instruction Input */}
          <div>
            <Label htmlFor="instruction">What would you like changed?</Label>
            <Textarea
              id="instruction"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder={config.placeholder}
              rows={4}
              className="mt-1.5"
              disabled={isSubmitting}
            />
          </div>

          {/* Preserve Existing Option */}
          {config.showPreserveOption && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="preserve"
                checked={preserveExisting}
                onCheckedChange={(checked) => setPreserveExisting(checked === true)}
                disabled={isSubmitting}
              />
              <Label htmlFor="preserve" className="text-sm cursor-pointer">
                {config.preserveLabel || 'Keep existing items, add new ones'}
              </Label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || !instruction.trim()}
            className="rounded-sm"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4 mr-2" />
                Submit Revision
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
