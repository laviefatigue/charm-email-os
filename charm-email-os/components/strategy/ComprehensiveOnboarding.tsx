'use client';

import { useState, useEffect } from 'react';
import {
  Building2,
  Package,
  Target,
  Users,
  Briefcase,
  MessageSquare,
  Trophy,
  Calendar,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Pencil,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { onboardingApi, type OnboardingSubmission } from '@/lib/api';
import { OnboardingEditModal } from './OnboardingEditModal';

interface ComprehensiveOnboardingProps {
  clientId: string;
}

function formatDate(dateString?: string) {
  if (!dateString) return 'N/A';
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function Section({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border rounded-lg">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between p-4 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">{title}</span>
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {isOpen && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        {label}
      </p>
      <p className="text-sm">{value || <span className="text-muted-foreground">Not specified</span>}</p>
    </div>
  );
}

function TagList({ items, emptyText = 'None specified' }: { items: string[]; emptyText?: string }) {
  if (!items || items.length === 0) {
    return <span className="text-sm text-muted-foreground">{emptyText}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <Badge key={item} variant="secondary" className="text-xs">
          {item}
        </Badge>
      ))}
    </div>
  );
}

export function ComprehensiveOnboarding({ clientId }: ComprehensiveOnboardingProps) {
  const [submission, setSubmission] = useState<OnboardingSubmission | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);

  useEffect(() => {
    async function fetchSubmission() {
      try {
        setLoading(true);
        const response = await onboardingApi.getSubmissions(clientId);
        // Get the most recent submission
        if (response.submissions.length > 0) {
          setSubmission(response.submissions[0]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load onboarding data');
      } finally {
        setLoading(false);
      }
    }

    fetchSubmission();
  }, [clientId]);

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="text-center">
            <div className="animate-pulse flex flex-col items-center gap-2">
              <div className="h-4 w-32 bg-muted rounded" />
              <div className="h-3 w-24 bg-muted rounded" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="text-center text-muted-foreground">
            <p>{error}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!submission) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="text-center">
            <ExternalLink className="h-10 w-10 mx-auto mb-3 text-muted-foreground opacity-50" />
            <p className="font-medium text-muted-foreground mb-2">
              No comprehensive onboarding form submitted
            </p>
            <p className="text-sm text-muted-foreground mb-4">
              Send the client the onboarding form to collect detailed context.
            </p>
            <Button variant="outline" asChild>
              <a
                href={`https://onboard.laviefatigue.com?client_id=${clientId}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Open Onboarding Form
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Building2 className="h-4 w-4" />
            Comprehensive Profile
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Submitted {formatDate(submission.submittedAt || submission.createdAt)}
          </p>
        </div>
        <Badge
          variant={submission.submissionStatus === 'completed' ? 'default' : 'secondary'}
        >
          {submission.submissionStatus}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Section 1: Foundation */}
        <Section icon={Building2} title="Foundation">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Field label="Company Name" value={submission.companyName} />
            <Field label="Website" value={submission.website} />
            <Field label="Contact Name" value={submission.contactName} />
            <Field label="Contact Email" value={submission.contactEmail} />
            <Field label="Employee Count" value={submission.employeeCount} />
            <Field label="Funding Stage" value={submission.fundingStage} />
            {submission.hqLocation && (
              <Field label="HQ Location" value={submission.hqLocation} />
            )}
          </div>
        </Section>

        {/* Section 2: Offering */}
        <Section icon={Package} title="Offering">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <Field label="Core Product/Service" value={submission.coreProduct} />
            </div>
            <Field label="Target Customer" value={submission.targetCustomer} />
            <div className="grid grid-cols-2 gap-4">
              <Field label="ACV" value={submission.acv} />
              <Field label="Sales Cycle" value={submission.salesCycleLength} />
            </div>
          </div>
        </Section>

        {/* Section 3: Market Signals */}
        <Section icon={Target} title="Market Signals" defaultOpen={false}>
          <div className="space-y-4">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Buying Signals
              </p>
              <TagList items={submission.signals} />
            </div>
          </div>
        </Section>

        {/* Section 4: Audience */}
        <Section icon={Users} title="Audience" defaultOpen={false}>
          <div className="space-y-4">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Target Job Titles
              </p>
              <TagList items={submission.jobTitles} />
            </div>

            {submission.segments.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Customer Segments
                </p>
                <div className="space-y-2">
                  {submission.segments.map((segment, i) => (
                    <div key={segment.id || i} className="bg-muted/50 rounded p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-sm">{segment.segmentName}</span>
                        <Badge variant="outline">{segment.revenuePercentage}% revenue</Badge>
                      </div>
                      {segment.uniqueCharacteristics && (
                        <p className="text-xs text-muted-foreground">{segment.uniqueCharacteristics}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {submission.personas.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Buyer Personas
                </p>
                <div className="space-y-2">
                  {submission.personas.map((persona, i) => (
                    <div key={persona.id || i} className="bg-muted/50 rounded p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-medium text-sm">{persona.jobTitle}</span>
                        {persona.seniorityLevel && (
                          <Badge variant="outline" className="text-xs">
                            {persona.seniorityLevel}
                          </Badge>
                        )}
                      </div>
                      {persona.painBeforeBuying && (
                        <p className="text-xs text-muted-foreground">
                          <strong>Pain:</strong> {persona.painBeforeBuying}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* Section 5: Process */}
        <Section icon={Briefcase} title="Current Process" defaultOpen={false}>
          <div className="space-y-4">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Outbound Tools
              </p>
              <TagList items={submission.outboundTools} />
            </div>
            <Field label="CRM" value={submission.crm} />
          </div>
        </Section>

        {/* Section 6: Messaging */}
        <Section icon={MessageSquare} title="Messaging" defaultOpen={false}>
          <div className="space-y-4">
            <Field label="Customer Voice" value={submission.customerVoice} />
            <Field label="ROI / Results" value={submission.roiResults} />
            <Field label="Tone Style" value={submission.toneStyle} />
          </div>
        </Section>

        {/* Section 7: Goals */}
        <Section icon={Trophy} title="Goals" defaultOpen={false}>
          <div className="space-y-4">
            <Field label="Primary GTM Objective" value={submission.primaryGtmObjective} />
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Success Metrics
              </p>
              <TagList items={submission.successMetrics} />
            </div>
            <Field label="Success Definition" value={submission.successDefinition} />
          </div>
        </Section>

        {/* Metadata */}
        <div className="pt-4 border-t flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Calendar className="h-3 w-3" />
            <span>Last updated: {formatDate(submission.updatedAt)}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setEditModalOpen(true)}
          >
            <Pencil className="h-3 w-3 mr-1" />
            Edit
          </Button>
        </div>
      </CardContent>

      {/* Edit Modal */}
      <OnboardingEditModal
        submission={submission}
        open={editModalOpen}
        onOpenChange={setEditModalOpen}
        onSave={(updated) => setSubmission(updated)}
      />
    </Card>
  );
}
