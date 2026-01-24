'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Copy, Check, Edit2, Clock, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { SequenceEmail } from '@/lib/api';

interface EmailStepCardProps {
  email: SequenceEmail;
  onEdit?: (position: number) => void;
  onRequestRevision?: (position: number) => void;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  highlightSpintax?: boolean;
  className?: string;
}

// Highlight spintax and liquid syntax in text
function renderWithSpintaxHighlight(text: string): React.ReactNode {
  if (!text) return text;

  // Split by spintax patterns {option1|option2} and liquid {% ... %} and {{ ... }}
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  // Combined regex for spintax {a|b|c}, liquid tags {% %}, and liquid vars {{ }}
  const regex = /(\{[^{}|]+(?:\|[^{}|]+)+\})|(\{%[^%]+%\})|(\{\{[^}]+\}\})/g;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    // Determine type and style
    const matchedText = match[0];
    if (match[1]) {
      // Spintax {option1|option2}
      parts.push(
        <span key={match.index} className="bg-purple-100 text-purple-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    } else if (match[2]) {
      // Liquid tag {% if %}{% endif %}
      parts.push(
        <span key={match.index} className="bg-blue-100 text-blue-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    } else if (match[3]) {
      // Liquid variable {{var}}
      parts.push(
        <span key={match.index} className="bg-green-100 text-green-800 rounded px-0.5 font-mono text-xs">
          {matchedText}
        </span>
      );
    }

    lastIndex = regex.lastIndex;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

const VALUE_PROP_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  save_time: { label: 'Save Time', icon: '\u23F1\uFE0F', color: 'bg-blue-100 text-blue-700' },
  save_money: { label: 'Save Money', icon: '\uD83D\uDCB5', color: 'bg-green-100 text-green-700' },
  make_money: { label: 'Make Money', icon: '\uD83D\uDCB0', color: 'bg-yellow-100 text-yellow-700' },
};

const STRATEGY_LABELS: Record<string, string> = {
  custom_signal: 'Custom Signal',
  creative_ideas: 'Creative Ideas',
  whole_offer: 'Whole Offer',
  case_study: 'Case Study',
  redirect: 'Redirect',
  fallback: 'Fallback',
};

export function EmailStepCard({
  email,
  onEdit,
  onRequestRevision,
  isExpanded = false,
  onToggleExpand,
  highlightSpintax = false,
  className,
}: EmailStepCardProps) {
  const [copied, setCopied] = useState<'subject' | 'body' | null>(null);

  const displaySubject = email.editedSubjectLine || email.subjectLine;
  const displayBody = email.editedEmailBody || email.emailBody;
  const isEdited = !!(email.editedSubjectLine || email.editedEmailBody);
  const valuePropInfo = email.valueProp ? VALUE_PROP_LABELS[email.valueProp] : null;
  const strategyLabel = email.strategy ? STRATEGY_LABELS[email.strategy] || email.strategy : null;

  const handleCopy = async (type: 'subject' | 'body') => {
    const text = type === 'subject' ? displaySubject : displayBody;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div
      className={cn(
        'border rounded-lg overflow-hidden',
        isExpanded ? 'bg-white' : 'bg-gray-50 hover:bg-gray-100',
        className
      )}
    >
      {/* Header - always visible */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer"
        onClick={onToggleExpand}
      >
        <div className="flex items-center gap-3">
          {/* Expand/collapse icon */}
          <button className="text-gray-400">
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {/* Position and timing */}
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">Email {email.position}</span>
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Day {email.waitDays}
            </span>
          </div>

          {/* Thread indicator */}
          {email.threadReply ? (
            <Badge variant="outline" className="text-xs bg-gray-100">
              <MessageSquare className="w-3 h-3 mr-1" />
              Threads
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
              New Thread
            </Badge>
          )}

          {/* Edited badge */}
          {isEdited && (
            <Badge variant="secondary" className="text-xs">
              Edited
            </Badge>
          )}
        </div>

        {/* Right side badges */}
        <div className="flex items-center gap-2">
          {valuePropInfo && (
            <Badge className={cn('text-xs', valuePropInfo.color)}>
              {valuePropInfo.icon} {valuePropInfo.label}
            </Badge>
          )}
          {email.wordCount && (
            <Badge variant="outline" className="text-xs">
              {email.wordCount} words
            </Badge>
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t px-4 py-3 space-y-3">
          {/* Subject line (for Email 1 and 3) */}
          {displaySubject && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-muted-foreground">Subject Line</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCopy('subject');
                  }}
                >
                  {copied === 'subject' ? (
                    <Check className="w-3 h-3 text-green-500" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                </Button>
              </div>
              <div className="bg-gray-50 rounded p-2 font-mono text-sm">
                {highlightSpintax ? renderWithSpintaxHighlight(displaySubject) : displaySubject}
              </div>
            </div>
          )}

          {/* Email body */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-muted-foreground">
                Email Body
                {strategyLabel && (
                  <span className="ml-2 text-gray-400">({strategyLabel})</span>
                )}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCopy('body');
                }}
              >
                {copied === 'body' ? (
                  <Check className="w-3 h-3 text-green-500" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
              </Button>
            </div>
            <pre className="bg-gray-50 rounded p-3 text-sm whitespace-pre-wrap font-sans leading-relaxed">
              {highlightSpintax ? renderWithSpintaxHighlight(displayBody) : displayBody}
            </pre>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2 border-t">
            {onEdit && (
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(email.position);
                }}
              >
                <Edit2 className="w-3 h-3 mr-1" />
                Edit
              </Button>
            )}
            {onRequestRevision && (
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onRequestRevision(email.position);
                }}
              >
                Request Revision for Email {email.position}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
