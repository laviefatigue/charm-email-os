'use client';

import { useState, useEffect } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { strategyApi, type Strategy } from '@/lib/api';
import { toast } from 'sonner';

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
  const [newStrategyName, setNewStrategyName] = useState('');
  const [newStrategyDescription, setNewStrategyDescription] = useState('');
  const [creating, setCreating] = useState(false);

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

  const handleCreate = async () => {
    if (!newStrategyName.trim()) return;

    setCreating(true);
    try {
      const strategy = await strategyApi.createStrategy(
        clientId,
        newStrategyName.trim(),
        newStrategyDescription.trim() || undefined
      );
      setStrategies([...strategies, strategy]);
      onStrategyChange(strategy.id);
      setCreateModalOpen(false);
      setNewStrategyName('');
      setNewStrategyDescription('');
      toast.success('Strategy created');
    } catch (err) {
      console.error('Failed to create strategy:', err);
      toast.error('Failed to create strategy');
    } finally {
      setCreating(false);
    }
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
              {strategy.name}
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

      {/* Create Strategy Modal */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Strategy</DialogTitle>
            <DialogDescription>
              Create a new strategy to organize campaign variants
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="strategy-name">Strategy Name</Label>
              <Input
                id="strategy-name"
                placeholder="e.g., Q1 Outreach Campaign"
                value={newStrategyName}
                onChange={(e) => setNewStrategyName(e.target.value)}
                disabled={creating}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="strategy-description">Description (optional)</Label>
              <Input
                id="strategy-description"
                placeholder="Brief description of this strategy"
                value={newStrategyDescription}
                onChange={(e) => setNewStrategyDescription(e.target.value)}
                disabled={creating}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateModalOpen(false)}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={creating || !newStrategyName.trim()}
            >
              {creating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Creating...
                </>
              ) : (
                'Create Strategy'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
