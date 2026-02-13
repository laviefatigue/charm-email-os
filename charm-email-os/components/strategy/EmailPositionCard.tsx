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
import { Star, Edit2, Copy, Clock, MessageSquare, Mail, Link2, Calendar, RefreshCw } from 'lucide-react';
import type { EmailPosition, EmailVariant, VariableSchema } from '@/lib/types';
import { campaignDocumentApi } from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { RequestRevisionButton } from './RequestRevisionButton';

// Core variables that are always purple
const CORE_VARIABLE_NAMES = ['first_name', 'company_name', 'role_title'];

interface EmailPositionCardProps {
  position: EmailPosition;
  documentId: string;
  onSelectVariant: (position: number, variantNumber: number) => void;
  onRefresh: () => void;
  variableSchema?: VariableSchema;
  onRequestRevision?: (emailPosition: number, variantNumber: number) => void;
  isRevising?: boolean;
}

// Determine variable type for coloring
function getVariableType(variableName: string, schema?: VariableSchema): 'core' | 'high_signal' | 'campaign' | 'ai_generated' {
  // Strip {{ }} if present
  const name = variableName.replace(/^\{\{|\}\}$/g, '');

  // Core variables are always purple
  if (CORE_VARIABLE_NAMES.includes(name)) {
    return 'core';
  }

  if (schema) {
    // Check high-signal variables (emerald)
    if (schema.highSignal?.some(v => v.name === name || v.name === `{{${name}}}`)) {
      return 'high_signal';
    }
    // Check AI-generated variables (blue)
    if (schema.aiGenerated?.some(v => v.name === name || v.name === `{{${name}}}`)) {
      return 'ai_generated';
    }
    // Check core schema variables (purple)
    if (schema.core?.some(v => v.name === name || v.name === `{{${name}}}`)) {
      return 'core';
    }
  }

  // Default to campaign variable (blue)
  return 'campaign';
}

// Variable type to color mapping
const VARIABLE_COLORS = {
  core: 'bg-purple-100 text-purple-800',        // Core variables - purple
  high_signal: 'bg-emerald-100 text-emerald-800', // High-signal - emerald
  campaign: 'bg-blue-100 text-blue-800',        // Campaign variables - blue
  ai_generated: 'bg-sky-100 text-sky-800',      // AI generated - sky blue
  spintax: 'bg-amber-100 text-amber-800',       // Spintax - amber
  liquid: 'bg-slate-100 text-slate-800',        // Liquid tags - slate
};

// Highlight variables in email body with schema-aware colors
function highlightVariables(text: string, schema?: VariableSchema): React.ReactNode {
  const parts = text.split(/(\{\{[^}]+\}\}|\{[^}|]+(?:\|[^}]+)*\}|{%[^%]+%})/g);

  return parts.map((part, idx) => {
    if (part.match(/^\{\{[^}]+\}\}$/)) {
      // {{variable}} - color based on variable type
      const varType = getVariableType(part, schema);
      return (
        <span key={idx} className={cn('px-1 rounded font-mono text-sm', VARIABLE_COLORS[varType])}>
          {part}
        </span>
      );
    }
    if (part.match(/^\{[^}|]+(?:\|[^}]+)*\}$/)) {
      // {spintax|options} - amber highlight
      return (
        <span key={idx} className={cn('px-1 rounded font-mono text-sm', VARIABLE_COLORS.spintax)}>
          {part}
        </span>
      );
    }
    if (part.match(/^{%[^%]+%}$/)) {
      // {% liquid %} - slate highlight
      return (
        <span key={idx} className={cn('px-1 rounded font-mono text-sm', VARIABLE_COLORS.liquid)}>
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
  variableSchema,
  onRequestRevision,
  isRevising,
}: {
  variant: EmailVariant;
  documentId: string;
  position: number;
  onSelectVariant: (position: number, variantNumber: number) => void;
  onRefresh: () => void;
  variableSchema?: VariableSchema;
  onRequestRevision?: (position: number, variantNumber: number) => void;
  isRevising?: boolean;
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
          <p className="font-medium">{highlightVariables(displaySubject, variableSchema)}</p>
        </div>
      )}

      {/* Email Body */}
      <div className="bg-background rounded-lg p-4 border whitespace-pre-wrap text-sm leading-relaxed">
        {highlightVariables(displayBody, variableSchema)}
      </div>

      {/* Stats Row + Revision Button */}
      <div className="flex items-center justify-between">
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
        {onRequestRevision && (
          <RequestRevisionButton
            onClick={() => onRequestRevision(position, variant.variantNumber)}
            isSubmitting={isRevising}
            label="Revise Email"
            tooltip={`Request revision for ${variant.variantName || `Variant ${variant.variantNumber}`}`}
          />
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
  variableSchema,
  onRequestRevision,
  isRevising,
}: EmailPositionCardProps) {
  const [activeVariant, setActiveVariant] = useState(
    position.variants.find(v => v.isRecommended)?.variantNumber.toString() ||
    position.variants[0]?.variantNumber.toString() ||
    '1'
  );

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Position Header */}
      <div className="bg-muted/50 px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h4 className="font-semibold">{position.title}</h4>
          {position.day !== undefined && (
            <Badge variant="outline" className="text-xs flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              Day {position.day}
            </Badge>
          )}
        </div>
        {position.threadBehavior && (
          <Badge
            variant={position.threadBehavior === 'new_thread' ? 'secondary' : 'outline'}
            className="text-xs flex items-center gap-1"
          >
            <Link2 className="h-3 w-3" />
            {position.threadBehavior === 'new_thread' ? 'New Thread' : position.threadBehavior.replace('threads_to_position_', 'Threads to #')}
          </Badge>
        )}
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
                variableSchema={variableSchema}
                onRequestRevision={onRequestRevision}
                isRevising={isRevising}
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
            variableSchema={variableSchema}
            onRequestRevision={onRequestRevision}
            isRevising={isRevising}
          />
        </div>
      )}

      {/* Subject Options (if present) - handles both subjectOptions and subjectLineOptions */}
      {((position.subjectOptions && position.subjectOptions.length > 0) ||
        (position.subjectLineOptions && position.subjectLineOptions.length > 0)) && (
        <div className="border-t bg-muted/30 p-4">
          <h5 className="text-xs font-semibold text-muted-foreground mb-2">Subject Line Options</h5>
          <div className="space-y-2">
            {(position.subjectOptions || position.subjectLineOptions || []).map((option, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="shrink-0">{idx + 1}</Badge>
                <div>
                  <p className="font-medium">{highlightVariables(option.subjectLine, variableSchema)}</p>
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
