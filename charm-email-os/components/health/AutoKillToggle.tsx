'use client';

import { useState } from 'react';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { Shield, AlertTriangle, Settings2 } from 'lucide-react';
import { AutoKillConfig } from '@/lib/types/inventory';

interface AutoKillToggleProps {
  config: AutoKillConfig;
  onConfigChange: (config: AutoKillConfig) => Promise<void>;
  isUpdating?: boolean;
  className?: string;
}

export function AutoKillToggle({
  config,
  onConfigChange,
  isUpdating = false,
  className,
}: AutoKillToggleProps) {
  const [showEnableDialog, setShowEnableDialog] = useState(false);
  const [showConfigDialog, setShowConfigDialog] = useState(false);
  const [pendingConfig, setPendingConfig] = useState<AutoKillConfig>(config);

  const handleToggleChange = (enabled: boolean) => {
    if (enabled) {
      // Show confirmation dialog when enabling
      setPendingConfig({ ...config, enabled: true });
      setShowEnableDialog(true);
    } else {
      // Disable immediately
      onConfigChange({ ...config, enabled: false });
    }
  };

  const handleEnableConfirm = async () => {
    await onConfigChange(pendingConfig);
    setShowEnableDialog(false);
  };

  const handleConfigSave = async () => {
    await onConfigChange(pendingConfig);
    setShowConfigDialog(false);
  };

  const openConfigDialog = () => {
    setPendingConfig(config);
    setShowConfigDialog(true);
  };

  return (
    <div className={cn('flex items-center gap-3', className)}>
      {/* Toggle */}
      <div className="flex items-center gap-2">
        <Switch
          id="auto-kill-toggle"
          checked={config.enabled}
          onCheckedChange={handleToggleChange}
          disabled={isUpdating}
          className={cn(
            config.enabled ? 'bg-emerald-600' : ''
          )}
        />
        <Label
          htmlFor="auto-kill-toggle"
          className="flex items-center gap-1.5 cursor-pointer"
        >
          <Shield className={cn('h-4 w-4', config.enabled ? 'text-emerald-600' : 'text-muted-foreground')} />
          <span className={cn('font-medium', config.enabled ? 'text-emerald-600' : '')}>
            Auto-Kill {config.enabled ? 'ON' : 'OFF'}
          </span>
        </Label>
      </div>

      {/* Config Button */}
      {config.enabled && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={openConfigDialog}
          disabled={isUpdating}
        >
          <Settings2 className="h-4 w-4" />
        </Button>
      )}

      {/* Enable Confirmation Dialog */}
      <Dialog open={showEnableDialog} onOpenChange={setShowEnableDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-emerald-600" />
              Enable Auto-Kill
            </DialogTitle>
            <DialogDescription>
              When enabled, inboxes that exceed bounce thresholds will be automatically
              killed and optionally replaced in their campaigns.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <div className="p-4 bg-yellow-50 dark:bg-yellow-950/30 rounded-lg border border-yellow-200 dark:border-yellow-900">
              <div className="flex gap-3">
                <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-medium text-yellow-800 dark:text-yellow-200">
                    Important
                  </div>
                  <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-1">
                    Auto-kill will immediately kill inboxes with 2+ hard bounces in 24h
                    or 0.5%+ hard bounce rate over 7 days. Killed inboxes cannot be recovered.
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Cooldown Period</Label>
                <Select
                  value={String(pendingConfig.cooldownHours)}
                  onValueChange={(value) =>
                    setPendingConfig({ ...pendingConfig, cooldownHours: Number(value) })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="24">24 hours</SelectItem>
                    <SelectItem value="48">48 hours (recommended)</SelectItem>
                    <SelectItem value="72">72 hours</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Warning inboxes will cool down for this period before returning to reserve
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enable-auto-replace"
                  checked={pendingConfig.autoReplace}
                  onChange={(e) =>
                    setPendingConfig({ ...pendingConfig, autoReplace: e.target.checked })
                  }
                  className="rounded"
                />
                <Label htmlFor="enable-auto-replace" className="font-normal">
                  Automatically replace killed inboxes in campaigns
                </Label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enable-notify"
                  checked={pendingConfig.notifyOnKill}
                  onChange={(e) =>
                    setPendingConfig({ ...pendingConfig, notifyOnKill: e.target.checked })
                  }
                  className="rounded"
                />
                <Label htmlFor="enable-notify" className="font-normal">
                  Send notification when inbox is killed
                </Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEnableDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleEnableConfirm}
              disabled={isUpdating}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {isUpdating ? 'Enabling...' : 'Enable Auto-Kill'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Configuration Dialog */}
      <Dialog open={showConfigDialog} onOpenChange={setShowConfigDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings2 className="h-5 w-5" />
              Auto-Kill Configuration
            </DialogTitle>
            <DialogDescription>
              Adjust how automatic inbox killing behaves.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <div className="space-y-2">
              <Label>Cooldown Period</Label>
              <Select
                value={String(pendingConfig.cooldownHours)}
                onValueChange={(value) =>
                  setPendingConfig({ ...pendingConfig, cooldownHours: Number(value) })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24">24 hours</SelectItem>
                  <SelectItem value="48">48 hours (recommended)</SelectItem>
                  <SelectItem value="72">72 hours</SelectItem>
                  <SelectItem value="96">96 hours</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Warning inboxes will cool down for this period before returning to reserve
              </p>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="config-auto-replace"
                checked={pendingConfig.autoReplace}
                onChange={(e) =>
                  setPendingConfig({ ...pendingConfig, autoReplace: e.target.checked })
                }
                className="rounded"
              />
              <Label htmlFor="config-auto-replace" className="font-normal">
                Automatically replace killed inboxes in campaigns
              </Label>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="config-notify"
                checked={pendingConfig.notifyOnKill}
                onChange={(e) =>
                  setPendingConfig({ ...pendingConfig, notifyOnKill: e.target.checked })
                }
                className="rounded"
              />
              <Label htmlFor="config-notify" className="font-normal">
                Send notification when inbox is killed
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfigDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleConfigSave} disabled={isUpdating}>
              {isUpdating ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
