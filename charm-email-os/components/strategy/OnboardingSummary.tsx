'use client';

import {
  Building2,
  Users,
  Package,
  Globe,
  Inbox,
  FileText,
  User,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { Client } from '@/lib/types';

interface OnboardingSummaryProps {
  client: Client;
}

export function OnboardingSummary({ client }: OnboardingSummaryProps) {
  const data = client.onboardingData;

  if (!data) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="text-center">
            <User className="h-10 w-10 mx-auto mb-3 text-muted-foreground opacity-50" />
            <p className="font-medium text-muted-foreground">
              No client profile data available
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <User className="h-4 w-4" />
          Client Profile
        </CardTitle>
      </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Primary Domain */}
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                <Globe className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Primary Domain
                </p>
                <p className="font-medium mt-0.5">{data.primaryDomain}</p>
              </div>
            </div>

            {/* Industry */}
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
                <Building2 className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Industry
                </p>
                <Badge variant="secondary" className="mt-1">
                  {data.industry}
                </Badge>
              </div>
            </div>

            {/* Inboxes Needed */}
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-50">
                <Inbox className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Inboxes Needed
                </p>
                <p className="font-medium mt-0.5">{data.inboxesNeeded} inboxes</p>
              </div>
            </div>

            {/* Contact Personas */}
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-50">
                <Users className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Sender Personas
                </p>
                {data.contactFirstNames && data.contactFirstNames.length > 0 ? (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {data.contactFirstNames.map((name) => (
                      <Badge key={name} variant="outline" className="text-xs">
                        {name}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground mt-0.5">None specified</p>
                )}
              </div>
            </div>

            {/* Product/Service - spans 2 columns on larger screens */}
            <div className="flex items-start gap-3 md:col-span-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 flex-shrink-0">
                <Package className="h-5 w-5 text-indigo-600" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Product / Service
                </p>
                <p className="text-sm mt-1 text-foreground">{data.product}</p>
              </div>
            </div>
          </div>

          {/* Notes - Full width if present */}
          {data.notes && (
            <div className="mt-6 pt-6 border-t">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 flex-shrink-0">
                  <FileText className="h-5 w-5 text-gray-600" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Additional Notes
                  </p>
                  <p className="text-sm mt-1 text-muted-foreground">{data.notes}</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
    </Card>
  );
}
