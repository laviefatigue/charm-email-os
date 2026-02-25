'use client';

import { useState } from 'react';
import {
  Building2,
  Globe,
  Mail,
  User,
  Pencil,
  Save,
  X,
  LinkIcon,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Switch } from '@/components/ui/switch';
import type { Client } from '@/lib/types';
import { INDUSTRIES } from '@/lib/types';
import { useClientStore } from '@/lib/stores/clientStore';

interface ClientProfileCardProps {
  client: Client;
  onUpdate?: (updatedClient: Client) => void;
}

export function ClientProfileCard({ client, onUpdate }: ClientProfileCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    contactName: client.contactName || '',
    contactEmail: client.contactEmail || '',
    website: client.website || '',
    industry: client.industry || '',
    domainPattern: client.domainPattern || '',
    syncEnabled: client.syncEnabled ?? true,  // Default to enabled
  });

  const handleSave = async () => {
    const { updateClient } = useClientStore.getState();
    setIsSaving(true);
    try {
      await updateClient(client.id, formData);
      // Store is updated, UI will refresh automatically
      onUpdate?.(client); // Call callback if provided (for backward compatibility)
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update client:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      contactName: client.contactName || '',
      contactEmail: client.contactEmail || '',
      website: client.website || '',
      industry: client.industry || '',
      domainPattern: client.domainPattern || '',
      syncEnabled: client.syncEnabled ?? true,
    });
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            Basic Information
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCancel}
              disabled={isSaving}
            >
              <X className="h-4 w-4 mr-1" />
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={isSaving}
            >
              <Save className="h-4 w-4 mr-1" />
              {isSaving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="contactName">Contact Name</Label>
              <Input
                id="contactName"
                value={formData.contactName}
                onChange={(e) =>
                  setFormData({ ...formData, contactName: e.target.value })
                }
                placeholder="John Smith"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contactEmail">Contact Email</Label>
              <Input
                id="contactEmail"
                type="email"
                value={formData.contactEmail}
                onChange={(e) =>
                  setFormData({ ...formData, contactEmail: e.target.value })
                }
                placeholder="john@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Website</Label>
              <Input
                id="website"
                value={formData.website}
                onChange={(e) =>
                  setFormData({ ...formData, website: e.target.value })
                }
                placeholder="https://example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="industry">Industry</Label>
              <Select
                value={formData.industry}
                onValueChange={(value) =>
                  setFormData({ ...formData, industry: value })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select industry" />
                </SelectTrigger>
                <SelectContent>
                  {INDUSTRIES.map((industry) => (
                    <SelectItem key={industry} value={industry}>
                      {industry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="domainPattern">Domain Pattern</Label>
              <Input
                id="domainPattern"
                value={formData.domainPattern}
                onChange={(e) =>
                  setFormData({ ...formData, domainPattern: e.target.value })
                }
                placeholder="example.com"
              />
              <p className="text-xs text-muted-foreground">
                Used for pattern-based domain generation (e.g., getexample.com, tryexample.com)
              </p>
            </div>

            {/* Sync Settings - Only show if workspace is linked */}
            {client.workspaceId && (
              <div className="space-y-2 md:col-span-2 pt-4 border-t">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="syncEnabled" className="text-base">Sync Enabled</Label>
                    <p className="text-xs text-muted-foreground">
                      When disabled, this workspace will be excluded from EmailBison sync operations
                    </p>
                  </div>
                  <Switch
                    id="syncEnabled"
                    checked={formData.syncEnabled}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, syncEnabled: checked })
                    }
                  />
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Building2 className="h-4 w-4" />
          Basic Information
        </CardTitle>
        <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
          <Pencil className="h-4 w-4 mr-1" />
          Edit
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Company Name */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
              <Building2 className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Company
              </p>
              <p className="font-medium mt-0.5">{client.name}</p>
            </div>
          </div>

          {/* Contact */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-50">
              <User className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Contact
              </p>
              <p className="font-medium mt-0.5">
                {client.contactName || <span className="text-muted-foreground">Not set</span>}
              </p>
            </div>
          </div>

          {/* Email */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
              <Mail className="h-5 w-5 text-purple-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Email
              </p>
              {client.contactEmail ? (
                <a
                  href={`mailto:${client.contactEmail}`}
                  className="font-medium mt-0.5 text-primary hover:underline"
                >
                  {client.contactEmail}
                </a>
              ) : (
                <p className="font-medium mt-0.5 text-muted-foreground">Not set</p>
              )}
            </div>
          </div>

          {/* Website */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-50">
              <Globe className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Website
              </p>
              {client.website ? (
                <a
                  href={client.website.startsWith('http') ? client.website : `https://${client.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium mt-0.5 text-primary hover:underline"
                >
                  {client.website}
                </a>
              ) : (
                <p className="font-medium mt-0.5 text-muted-foreground">Not set</p>
              )}
            </div>
          </div>

          {/* Industry */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
              <Building2 className="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Industry
              </p>
              <p className="font-medium mt-0.5">
                {client.industry || <span className="text-muted-foreground">Not set</span>}
              </p>
            </div>
          </div>

          {/* Domain Pattern */}
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-pink-50">
              <LinkIcon className="h-5 w-5 text-pink-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Domain Pattern
              </p>
              <p className="font-medium mt-0.5">
                {client.domainPattern || <span className="text-muted-foreground">Not set</span>}
              </p>
            </div>
          </div>
        </div>

        {/* Workspace Info & Sync Status */}
        {client.workspaceName && (
          <div className="mt-6 pt-6 border-t">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Building2 className="h-4 w-4" />
                <span>
                  Linked to workspace: <strong>{client.workspaceName}</strong>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <RefreshCw className={`h-4 w-4 ${client.syncEnabled !== false ? 'text-green-600' : 'text-gray-400'}`} />
                <span className={`text-sm font-medium ${client.syncEnabled !== false ? 'text-green-600' : 'text-gray-500'}`}>
                  {client.syncEnabled !== false ? 'Sync Enabled' : 'Sync Disabled'}
                </span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
