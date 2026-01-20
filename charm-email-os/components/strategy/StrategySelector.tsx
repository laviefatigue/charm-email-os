'use client';

import { useState, useEffect } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { strategyApi, type Strategy } from '@/lib/api';
import { toast } from 'sonner';
import { NewStrategyModal } from './NewStrategyModal';

interface StrategySelectorProps {
  clientId: string;
  selectedStrategyId: string | null;
  onStrategyChange: (strategyId: string | null) => void;
}

export function StrategySelector({
  clientId,
  selectedStrategyId,
  onStrategyChange,
}: StrategySelectorProps) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const fetchStrategies = async () => {
    try {
      setLoading(true);
      const response = await strategyApi.getStrategies(clientId);
      setStrategies(response.strategies);
    } catch (err) {
      console.error('Failed to fetch strategies:', err);
      toast.error('Failed to load strategies');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStrategies();
  }, [clientId]);

  const handleStrategyCreated = (strategy: Strategy) => {
    setStrategies(prev => [...prev, strategy]);
    onStrategyChange(strategy.id);
  };

  return (
    <div className="flex items-center gap-2">
      <Label className="text-sm text-muted-foreground whitespace-nowrap">Strategy:</Label>
      <Select
        value={selectedStrategyId || 'all'}
        onValueChange={(value) => onStrategyChange(value === 'all' ? null : value)}
        disabled={loading}
      >
        <SelectTrigger className="w-[200px]">
          {loading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Loading...</span>
            </div>
          ) : (
            <SelectValue placeholder="All Strategies" />
          )}
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Strategies</SelectItem>
          {strategies.map((strategy) => (
            <SelectItem key={strategy.id} value={strategy.id}>
              <div className="flex flex-col">
                <span>{strategy.name}</span>
                {strategy.submissionCreatedAt && (
                  <span className="text-xs text-muted-foreground">
                    Based on {new Date(strategy.submissionCreatedAt).toLocaleDateString()}
                  </span>
                )}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="sm"
        onClick={() => setCreateModalOpen(true)}
        className="gap-1"
      >
        <Plus className="h-4 w-4" />
        New
      </Button>

      {/* New Strategy Modal with two options */}
      <NewStrategyModal
        clientId={clientId}
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        onStrategyCreated={handleStrategyCreated}
      />
    </div>
  );
}
