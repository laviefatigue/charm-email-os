'use client';

import { useEffect, useState } from 'react';
import { Inbox, Megaphone, Building2, Link2, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useClientStore } from '@/lib/stores';
import type { Workspace } from '@/lib/types';

interface WorkspaceSelectorProps {
  clientId: string;
  currentWorkspaceId?: string;
  onWorkspaceLinked?: (workspaceId: string) => void;
}

export function WorkspaceSelector({
  clientId,
  currentWorkspaceId,
  onWorkspaceLinked,
}: WorkspaceSelectorProps) {
  const { workspaces, fetchWorkspaces, linkWorkspace, isLoading, error } = useClientStore();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | undefined>(
    currentWorkspaceId
  );
  const [isLinking, setIsLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  useEffect(() => {
    setSelectedWorkspaceId(currentWorkspaceId);
  }, [currentWorkspaceId]);

  const selectedWorkspace = workspaces.find((w) => w.id === selectedWorkspaceId);

  const handleLinkWorkspace = async () => {
    if (!selectedWorkspaceId) return;

    setIsLinking(true);
    setLinkError(null);

    try {
      await linkWorkspace(clientId, selectedWorkspaceId);
      onWorkspaceLinked?.(selectedWorkspaceId);
    } catch (err) {
      setLinkError((err as Error).message);
    } finally {
      setIsLinking(false);
    }
  };

  const isCurrentlyLinked = currentWorkspaceId === selectedWorkspaceId;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="h-5 w-5" />
          Link to OwnRBL Workspace
        </CardTitle>
        <CardDescription>
          Connect this client to an existing OwnRBL workspace to sync inboxes, domains, and campaigns.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {linkError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{linkError}</AlertDescription>
          </Alert>
        )}

        <div className="space-y-2">
          <label className="text-sm font-medium">Select Workspace</label>
          <Select
            value={selectedWorkspaceId}
            onValueChange={setSelectedWorkspaceId}
            disabled={isLoading}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={isLoading ? 'Loading workspaces...' : 'Select a workspace'} />
            </SelectTrigger>
            <SelectContent>
              {workspaces.map((workspace) => (
                <SelectItem key={workspace.id} value={workspace.id}>
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-muted-foreground" />
                    <span>{workspace.workspaceName}</span>
                    <Badge variant="secondary" className="ml-2 text-xs">
                      {workspace.senderAccountCount} inboxes
                    </Badge>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {selectedWorkspace && (
          <div className="rounded-lg border bg-muted/50 p-4">
            <h4 className="font-medium mb-3">{selectedWorkspace.workspaceName}</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Inbox className="h-4 w-4" />
                <span>{selectedWorkspace.senderAccountCount} inboxes</span>
              </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <Megaphone className="h-4 w-4" />
                <span>{selectedWorkspace.campaignCount} campaigns</span>
              </div>
            </div>
            {selectedWorkspace.automationEnabled && (
              <Badge className="mt-3" variant="outline">
                Automation Enabled
              </Badge>
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button
            onClick={handleLinkWorkspace}
            disabled={!selectedWorkspaceId || isLinking || isCurrentlyLinked}
          >
            {isLinking ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Linking...
              </>
            ) : isCurrentlyLinked ? (
              <>
                <Link2 className="h-4 w-4 mr-2" />
                Currently Linked
              </>
            ) : (
              <>
                <Link2 className="h-4 w-4 mr-2" />
                Link Workspace
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
