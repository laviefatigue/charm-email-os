'use client';

import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
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
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import type { StrategySuggestion } from '@/lib/api';

interface SuggestionEditModalProps {
  suggestion: StrategySuggestion | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (id: string, data: { subjectLine: string; emailBody: string }) => Promise<void>;
}

export function SuggestionEditModal({
  suggestion,
  open,
  onOpenChange,
  onSave,
}: SuggestionEditModalProps) {
  const [subjectLine, setSubjectLine] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [saving, setSaving] = useState(false);

  // Initialize form from suggestion
  useEffect(() => {
    if (suggestion) {
      // Use edited version if exists, otherwise use original
      setSubjectLine(suggestion.editedSubjectLine || suggestion.subjectLine);
      setEmailBody(suggestion.editedEmailBody || suggestion.emailBody);
    }
  }, [suggestion]);

  const handleSave = async () => {
    if (!suggestion) return;

    setSaving(true);
    try {
      await onSave(suggestion.id, { subjectLine, emailBody });
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = suggestion && (
    subjectLine !== (suggestion.editedSubjectLine || suggestion.subjectLine) ||
    emailBody !== (suggestion.editedEmailBody || suggestion.emailBody)
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Edit Campaign Variant</DialogTitle>
          <DialogDescription>
            Edit the subject line and email body. Changes are saved as edited versions.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          {/* Metadata */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">V{suggestion?.variantNumber}</Badge>
            {suggestion?.score !== undefined && (
              <span className="font-mono">Score: {suggestion.score}</span>
            )}
            {suggestion?.campaignType && (
              <Badge variant="secondary">{suggestion.campaignType}</Badge>
            )}
          </div>

          {/* Subject Line */}
          <div className="grid gap-2">
            <Label htmlFor="subject">Subject Line</Label>
            <Input
              id="subject"
              placeholder="Enter subject line..."
              value={subjectLine}
              onChange={(e) => setSubjectLine(e.target.value)}
              disabled={saving}
            />
          </div>

          {/* Email Body */}
          <div className="grid gap-2">
            <Label htmlFor="body">Email Body</Label>
            <Textarea
              id="body"
              placeholder="Enter email body with {{variables}}..."
              value={emailBody}
              onChange={(e) => setEmailBody(e.target.value)}
              disabled={saving}
              rows={12}
              className="font-mono text-sm"
            />
          </div>

          {/* Variables info */}
          {suggestion?.usedVariables && suggestion.usedVariables.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-xs text-muted-foreground mr-1">Variables:</span>
              {suggestion.usedVariables.map((v, i) => (
                <Badge key={i} variant="outline" className="text-xs font-mono">
                  {v}
                </Badge>
              ))}
            </div>
          )}

          {/* Rationale */}
          {suggestion?.rationale && (
            <div className="text-sm text-muted-foreground border-l-2 border-blue-200 pl-3">
              <span className="font-medium">Original Rationale:</span> {suggestion.rationale}
            </div>
          )}
        </div>

        <DialogFooter className="border-t pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || !hasChanges}
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Saving...
              </>
            ) : (
              'Save Changes'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
