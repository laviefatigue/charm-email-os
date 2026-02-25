'use client';

import { useState, useEffect } from 'react';
import { AlertTriangle, Copy, ChevronDown, ChevronUp, RefreshCw, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { inboxApi } from '@/lib/api';
import type { Inbox } from '@/lib/types';

interface DisconnectedInboxesListProps {
  clientId: string;
}

export function DisconnectedInboxesList({ clientId }: DisconnectedInboxesListProps) {
  const [inboxes, setInboxes] = useState<Inbox[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchDisconnectedInboxes = async () => {
    try {
      // Fetch inboxes with status='Not connected' that aren't killed
      const response = await inboxApi.list({
        clientId,
        status: 'Not connected',
        pageSize: 500,
      });

      // Filter out killed inboxes (inbox_state = 'dead')
      const disconnected = response.items.filter(
        (inbox) => inbox.inboxState !== 'dead'
      );

      setInboxes(disconnected);
    } catch (error) {
      console.error('Failed to fetch disconnected inboxes:', error);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDisconnectedInboxes();
  }, [clientId]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchDisconnectedInboxes();
  };

  const handleCopyAll = async () => {
    const emailList = inboxes.map((inbox) => inbox.email).join('\n');
    try {
      await navigator.clipboard.writeText(emailList);
      toast.success(`Copied ${inboxes.length} email addresses to clipboard`);
    } catch (error) {
      console.error('Failed to copy:', error);
      toast.error('Failed to copy to clipboard');
    }
  };

  // Don't render if no disconnected inboxes
  if (!isLoading && inboxes.length === 0) {
    return null;
  }

  return (
    <Card className="border-amber-200 bg-amber-50/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <CardTitle className="text-base">Disconnected Inboxes</CardTitle>
            {!isLoading && (
              <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-300">
                {inboxes.length} need reconnection
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={isRefreshing}
            >
              {isRefreshing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
            </Button>
            {inboxes.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyAll}
                className="text-amber-700 hover:text-amber-800 hover:bg-amber-100"
              >
                <Copy className="h-4 w-4 mr-1" />
                Copy All
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        <CardDescription className="text-amber-700">
          These inboxes are disconnected in EmailBison and need to be reconnected via Hypertide
        </CardDescription>
      </CardHeader>

      {isExpanded && (
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-6 w-6 animate-spin text-amber-600" />
            </div>
          ) : (
            <div className="space-y-2">
              {/* Group by domain for easier reading */}
              {Object.entries(
                inboxes.reduce((acc, inbox) => {
                  const domain = inbox.email.split('@')[1] || 'unknown';
                  if (!acc[domain]) acc[domain] = [];
                  acc[domain].push(inbox);
                  return acc;
                }, {} as Record<string, Inbox[]>)
              ).map(([domain, domainInboxes]) => (
                <div key={domain} className="border rounded-lg p-3 bg-white">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-sm">{domain}</span>
                    <Badge variant="secondary" className="text-xs">
                      {domainInboxes.length} disconnected
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {domainInboxes.map((inbox) => (
                      <Badge
                        key={inbox.id}
                        variant="outline"
                        className="text-xs font-mono bg-amber-50"
                      >
                        {inbox.email.split('@')[0]}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
