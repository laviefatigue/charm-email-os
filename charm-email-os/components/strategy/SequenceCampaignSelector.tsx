'use client';

import { Mail, Star, Clock, Check, Sparkles, Send } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { CampaignSequence } from '@/lib/api';

interface SequenceCampaignSelectorProps {
  sequences: CampaignSequence[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  className?: string;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Pending' },
  approved: { bg: 'bg-green-100', text: 'text-green-700', label: 'Approved' },
  denied: { bg: 'bg-red-100', text: 'text-red-700', label: 'Denied' },
  revision_requested: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Revision' },
  spintax_pending: { bg: 'bg-purple-100', text: 'text-purple-700', label: 'Processing' },
  spintaxed: { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'Spintaxed' },
  sent: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Sent' },
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock className="w-3 h-3" />,
  approved: <Check className="w-3 h-3" />,
  spintaxed: <Sparkles className="w-3 h-3" />,
  sent: <Send className="w-3 h-3" />,
};

export function SequenceCampaignSelector({
  sequences,
  selectedId,
  onSelect,
  className,
}: SequenceCampaignSelectorProps) {
  const selectedSequence = selectedId ? sequences.find(s => s.id === selectedId) : null;

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Label className="text-sm text-muted-foreground whitespace-nowrap">
        <Mail className="w-4 h-4 inline mr-1" />
        Campaign:
      </Label>
      <Select
        value={selectedId || ''}
        onValueChange={(value) => onSelect(value || null)}
      >
        <SelectTrigger className="w-[350px]">
          <SelectValue placeholder="Select a campaign...">
            {selectedSequence && (
              <div className="flex items-center gap-2 overflow-hidden">
                <span className="truncate">{selectedSequence.campaignName}</span>
                {selectedSequence.score && (
                  <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
                    <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
                    {selectedSequence.score}
                  </span>
                )}
              </div>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {sequences.length === 0 ? (
            <div className="px-2 py-4 text-center text-sm text-muted-foreground">
              No campaigns available
            </div>
          ) : (
            sequences.map((sequence) => {
              const statusStyle = STATUS_STYLES[sequence.status] || STATUS_STYLES.pending;
              return (
                <SelectItem key={sequence.id} value={sequence.id}>
                  <div className="flex items-center gap-2 w-full">
                    <Badge
                      className={cn(
                        'text-[10px] px-1.5 py-0 h-5 flex items-center gap-1',
                        statusStyle.bg,
                        statusStyle.text
                      )}
                    >
                      {STATUS_ICONS[sequence.status]}
                      {statusStyle.label}
                    </Badge>
                    <span className="truncate flex-1">{sequence.campaignName}</span>
                    {sequence.score && (
                      <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
                        <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
                        {sequence.score}
                      </span>
                    )}
                  </div>
                </SelectItem>
              );
            })
          )}
        </SelectContent>
      </Select>
    </div>
  );
}
