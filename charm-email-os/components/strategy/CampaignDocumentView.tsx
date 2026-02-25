'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Sparkles, ChevronDown, ChevronUp, Star, Edit2, Check, X, FileText } from 'lucide-react';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ICPMappingSection } from './ICPMappingSection';
import { VariableSchemaSection } from './VariableSchemaSection';
import { EmailPositionCard } from './EmailPositionCard';
import { QAScoringCard } from './QAScoringCard';
import { StrategyNotesSection } from './StrategyNotesSection';
import { SequenceTimeline } from './SequenceTimeline';
import { campaignDocumentApi } from '@/lib/api';
import type { CampaignDocument, ClientDocumentsResponse } from '@/lib/types';
import { DOCUMENT_STATUS_COLORS } from '@/lib/types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface CampaignDocumentViewProps {
  clientId: string;
  className?: string;
}

export function CampaignDocumentView({ clientId, className }: CampaignDocumentViewProps) {
  const [documents, setDocuments] = useState<CampaignDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState({
    icp: true,
    variables: false,
    timeline: true,
    qa: true,
    notes: true,
  });

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const response: ClientDocumentsResponse = await campaignDocumentApi.getClientDocuments(clientId);
      setDocuments(response.documents);

      // Auto-select first document if none selected
      if (response.documents.length > 0 && !selectedDocId) {
        setSelectedDocId(response.documents[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch documents:', error);
      toast.error('Failed to load campaign documents');
    } finally {
      setLoading(false);
    }
  }, [clientId, selectedDocId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Get selected document
  const selectedDoc = selectedDocId
    ? documents.find(d => d.id === selectedDocId)
    : null;

  // Handle review action
  const handleReview = async (action: 'approve' | 'deny' | 'revision_requested') => {
    if (!selectedDoc) return;

    try {
      await campaignDocumentApi.reviewDocument(selectedDoc.id, action);
      toast.success(`Document ${action === 'approve' ? 'approved' : action === 'deny' ? 'denied' : 'revision requested'}`);
      fetchDocuments();
    } catch (error) {
      console.error('Failed to review document:', error);
      toast.error('Failed to update document status');
    }
  };

  // Handle variant selection
  const handleSelectVariant = async (position: number, variantNumber: number) => {
    if (!selectedDoc) return;

    try {
      await campaignDocumentApi.selectRecommended(selectedDoc.id, position, variantNumber);
      toast.success('Variant marked as recommended');
      fetchDocuments();
    } catch (error) {
      console.error('Failed to select variant:', error);
      toast.error('Failed to update recommended variant');
    }
  };

  // Toggle section
  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  if (loading) {
    return (
      <Card className={cn('animate-pulse', className)}>
        <CardHeader>
          <div className="h-6 w-48 bg-muted rounded" />
          <div className="h-4 w-32 bg-muted rounded mt-2" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="h-32 bg-muted rounded" />
            <div className="h-48 bg-muted rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (documents.length === 0) {
    return (
      <Card className={className}>
        <CardContent className="py-12 text-center">
          <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">No campaign documents yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Generate a strategy to create your first campaign document
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Document Selector */}
      {documents.length > 1 && (
        <Card>
          <CardContent className="py-3">
            <div className="flex items-center gap-4 overflow-x-auto">
              {documents.map((doc) => {
                const statusColors = DOCUMENT_STATUS_COLORS[doc.status] || DOCUMENT_STATUS_COLORS.draft;
                return (
                  <button
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded-lg border transition-all whitespace-nowrap',
                      selectedDocId === doc.id
                        ? 'border-primary bg-primary/5'
                        : 'border-transparent hover:border-muted-foreground/20'
                    )}
                  >
                    <FileText className="h-4 w-4" />
                    <span className="font-medium">{doc.documentName}</span>
                    <Badge variant="outline" className={cn(statusColors.bg, statusColors.text, 'text-xs')}>
                      {doc.status}
                    </Badge>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {selectedDoc && (
        <>
          {/* Document Header */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-xl">{selectedDoc.documentName}</CardTitle>
                  {selectedDoc.vertical && (
                    <Badge variant="secondary" className="mt-2">
                      {selectedDoc.vertical}
                    </Badge>
                  )}
                  {selectedDoc.objective && (
                    <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
                      {selectedDoc.objective}
                    </p>
                  )}
                </div>

                {/* Review Actions */}
                {selectedDoc.status === 'draft' && (
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReview('deny')}
                    >
                      <X className="h-4 w-4 mr-1" />
                      Deny
                    </Button>
                    <Button
                      size="sm"
                      variant="default"
                      onClick={() => handleReview('approve')}
                    >
                      <Check className="h-4 w-4 mr-1" />
                      Approve
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
          </Card>

          {/* Sequence Timeline */}
          {selectedDoc.sequenceSummary && selectedDoc.sequenceSummary.length > 0 && (
            <Collapsible open={expandedSections.timeline} onOpenChange={() => toggleSection('timeline')}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Sequence Overview</CardTitle>
                      {expandedSections.timeline ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent>
                    <SequenceTimeline steps={selectedDoc.sequenceSummary} />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          )}

          {/* ICP Mapping */}
          {selectedDoc.icpMapping && (
            <Collapsible open={expandedSections.icp} onOpenChange={() => toggleSection('icp')}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">ICP & Objection Mapping</CardTitle>
                      {expandedSections.icp ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent>
                    <ICPMappingSection icpMapping={selectedDoc.icpMapping} />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          )}

          {/* Variable Schema */}
          {selectedDoc.variableSchema && (
            <Collapsible open={expandedSections.variables} onOpenChange={() => toggleSection('variables')}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Variable Schema</CardTitle>
                      {expandedSections.variables ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent>
                    <VariableSchemaSection schema={selectedDoc.variableSchema} />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          )}

          {/* Email Positions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Email Sequence</CardTitle>
              <CardDescription>
                {selectedDoc.emailPositions.length} positions with multiple variants each
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {selectedDoc.emailPositions.map((position) => (
                <EmailPositionCard
                  key={position.position}
                  position={position}
                  documentId={selectedDoc.id}
                  onSelectVariant={handleSelectVariant}
                  onRefresh={fetchDocuments}
                />
              ))}
            </CardContent>
          </Card>

          {/* QA Scoring */}
          {selectedDoc.qaScoring && (
            <Collapsible open={expandedSections.qa} onOpenChange={() => toggleSection('qa')}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">QA Scoring</CardTitle>
                      {expandedSections.qa ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent>
                    <QAScoringCard scoring={selectedDoc.qaScoring} />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          )}

          {/* Strategy Notes */}
          {selectedDoc.strategyNotes && (
            <Collapsible open={expandedSections.notes} onOpenChange={() => toggleSection('notes')}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Strategy Notes</CardTitle>
                      {expandedSections.notes ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent>
                    <StrategyNotesSection notes={selectedDoc.strategyNotes} />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          )}
        </>
      )}
    </div>
  );
}
