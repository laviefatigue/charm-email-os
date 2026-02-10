'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Star, Edit2, Copy, Clock, MessageSquare, Mail } from 'lucide-react';
import type { EmailPosition, EmailVariant } from '@/lib/types';
import { campaignDocumentApi } from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface EmailPositionCardProps {
  position: EmailPosition;
  documentId: string;
  onSelectVariant: (position: number, variantNumber: number) => void;
  onRefresh: () => void;
}

// Highlight variables in email body
function highlightVariables(text: string): React.ReactNode {
  const parts = text.split(/(\{\{[^}]+\}\}|\{[^}|]+(?:\|[^}]+)*\}|{%[^%]+%})/g);

  return parts.map((part, idx) => {
    if (part.match(/^\{\{[^}]+\}\}$/)) {
      // {{variable}} - green highlight
      return (
        <span key={idx} className="bg-emerald-100 text-emerald-800 px-1 rounded font-mono text-sm">
          {part}
        </span>
      );
    }
    if (part.match(/^\{[^}|]+(?:\|[^}]+)*\}$/)) {
      // {spintax|options} - purple highlight
      return (
        <span key={idx} className="bg-purple-100 text-purple-800 px-1 rounded font-mono text-sm">
          {part}
        </span>
      );
    }
    if (part.match(/^{%[^%]+%}$/)) {
      // {% liquid %} - blue highlight
      return (
        <span key={idx} className="bg-blue-100 text-blue-800 px-1 rounded font-mono text-sm">
          {part}
        </span>
      );
    }
    return part;
  });
}

function VariantContent({
  variant,
  documentId,
  position,
  onSelectVariant,
  onRefresh,
}: {
  variant: EmailVariant;
  documentId: string;
  position: number;
  onSelectVariant: (position: number, variantNumber: number) => void;
  onRefresh: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editSubject, setEditSubject] = useState(variant.editedSubjectLine || variant.subjectLine || '');
  const [editBody, setEditBody] = useState(variant.editedEmailBody || variant.emailBody);
  const [saving, setSaving] = useState(false);

  const displaySubject = variant.editedSubjectLine || variant.subjectLine;
  const displayBody = variant.editedEmailBody || variant.emailBody;

  const handleSave = async () => {
    if (!variant.id) return;
    setSaving(true);
    try {
      await campaignDocumentApi.editVariant(documentId, variant.id, {
        subjectLine: editSubject || undefined,
        emailBody: editBody,
      });
      toast.success('Variant updated');
      setIsEditing(false);
      onRefresh();
    } catch (error) {
      console.error('Failed to save variant:', error);
      toast.error('Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = () => {
    const text = displaySubject
      ? `Subject: ${displaySubject}\n\n${displayBody}`
      : displayBody;
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  return (
    <div className="space-y-4">
      {/* Variant Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium">{variant.variantName || `Variant ${variant.variantNumber}`}</span>
          {variant.isRecommended && (
            <Badge variant="default" className="bg-amber-500 hover:bg-amber-600">
              <Star className="h-3 w-3 mr-1" />
              Recommended
            </Badge>
          )}
          {variant.strategy && (
            <Badge variant="outline" className="text-xs">
              {variant.strategy}
            </Badge>
          )}
          {variant.valueProp && (
            <Badge variant="secondary" className="text-xs">
              {variant.valueProp}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!variant.isRecommended && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onSelectVariant(position, variant.variantNumber)}
            >
              <Star className="h-4 w-4 mr-1" />
              Set Recommended
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setIsEditing(true)}>
            <Edit2 className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="ghost" onClick={handleCopy}>
            <Copy className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Subject Line */}
      {displaySubject && (
        <div className="bg-muted/50 rounded-lg p-3 border">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <Mail className="h-3 w-3" />
            Subject Line
          </div>
          <p className="font-medium">{highlightVariables(displaySubject)}</p>
        </div>
      )}

      {/* Email Body */}
      <div className="bg-background rounded-lg p-4 border whitespace-pre-wrap text-sm leading-relaxed">
        {highlightVariables(displayBody)}
      </div>

      {/* Stats Row */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {variant.wordCount && (
          <span className="flex items-center gap-1">
            <MessageSquare className="h-3 w-3" />
            {variant.wordCount} words
          </span>
        )}
        {variant.themUsRatio && (
          <span>Them:Us {variant.themUsRatio}</span>
        )}
        {variant.score && (
          <span className={cn(
            'font-medium',
            variant.score >= 85 ? 'text-emerald-600' :
            variant.score >= 70 ? 'text-amber-600' : 'text-red-600'
          )}>
            Score: {variant.score}
          </span>
        )}
        {variant.waitDays > 0 && (
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            +{variant.waitDays} days
          </span>
        )}
        {variant.threadReply && (
          <Badge variant="outline" className="text-xs">
            Thread Reply
          </Badge>
        )}
      </div>

      {/* Edit Dialog */}
      <Dialog open={isEditing} onOpenChange={setIsEditing}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit {variant.variantName || `Variant ${variant.variantNumber}`}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {displaySubject !== undefined && (
              <div>
                <Label>Subject Line</Label>
                <Input
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  placeholder="Subject line..."
                />
              </div>
            )}
            <div>
              <Label>Email Body</Label>
              <Textarea
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                rows={10}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function EmailPositionCard({
  position,
  documentId,
  onSelectVariant,
  onRefresh,
}: EmailPositionCardProps) {
  const [activeVariant, setActiveVariant] = useState(
    position.variants.find(v => v.isRecommended)?.variantNumber.toString() ||
    position.variants[0]?.variantNumber.toString() ||
    '1'
  );

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Position Header */}
      <div className="bg-muted/50 px-4 py-3 border-b">
        <h4 className="font-semibold">{position.title}</h4>
      </div>

      {/* Variant Tabs */}
      {position.variants.length > 1 ? (
        <Tabs value={activeVariant} onValueChange={setActiveVariant} className="p-4">
          <TabsList className="mb-4">
            {position.variants.map((variant) => (
              <TabsTrigger
                key={variant.variantNumber}
                value={variant.variantNumber.toString()}
                className="flex items-center gap-1"
              >
                V{variant.variantNumber}
                {variant.isRecommended && <Star className="h-3 w-3 text-amber-500" />}
              </TabsTrigger>
            ))}
          </TabsList>
          {position.variants.map((variant) => (
            <TabsContent key={variant.variantNumber} value={variant.variantNumber.toString()}>
              <VariantContent
                variant={variant}
                documentId={documentId}
                position={position.position}
                onSelectVariant={onSelectVariant}
                onRefresh={onRefresh}
              />
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <div className="p-4">
          <VariantContent
            variant={position.variants[0]}
            documentId={documentId}
            position={position.position}
            onSelectVariant={onSelectVariant}
            onRefresh={onRefresh}
          />
        </div>
      )}

      {/* Subject Options (if present) */}
      {position.subjectOptions && position.subjectOptions.length > 0 && (
        <div className="border-t bg-muted/30 p-4">
          <h5 className="text-xs font-semibold text-muted-foreground mb-2">Subject Line Options</h5>
          <div className="space-y-2">
            {position.subjectOptions.map((option, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="shrink-0">{idx + 1}</Badge>
                <div>
                  <p className="font-medium">{highlightVariables(option.subjectLine)}</p>
                  <p className="text-xs text-muted-foreground">{option.rationale}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
