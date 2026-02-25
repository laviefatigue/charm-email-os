'use client';

import { useMemo, useState, useCallback, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { CycleHeader } from './CycleHeader';
import { CycleVariablesPanel } from './CycleVariablesPanel';
import { CampaignGrid } from './CampaignGrid';
import { ICPMappingSection } from './ICPMappingSection';
import { RegenerationModal, type RegenerationModalConfig } from './RegenerationModal';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown, Target, Variable } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { unifiedCycleApi, strategyApi, campaignDocumentApi } from '@/lib/api';
import type {
  UnifiedCycleData,
  UnifiedCampaign,
  UnifiedEmail,
  CycleVariable,
  RegenerationSection,
  ICPSubSection,
  RegenerationScope,
  CampaignStatus,
  CampaignDocument,
  CampaignAngle,
} from '@/lib/types';

interface UnifiedCycleViewProps {
  clientId: string;
  cycleId?: string;
  className?: string;
}

// Modal configuration types
interface RegenerationState {
  isOpen: boolean;
  config: RegenerationModalConfig;
  section: RegenerationSection;
  subSection?: ICPSubSection;
  scope?: RegenerationScope;
}

// Transform a CampaignDocument into UnifiedCycleData format
function transformDocumentToCycleData(doc: CampaignDocument): UnifiedCycleData {
  // Extract variables from schema
  const coreVars: CycleVariable[] = (doc.variableSchema?.core || []).map(v => ({
    name: `{{${v.name}}}`,
    description: v.description || '',
    source: v.source || undefined,
  }));

  const highSignalVars: CycleVariable[] = (doc.variableSchema?.highSignal || []).map(v => ({
    name: `{{${v.name}}}`,
    description: v.description || '',
    source: v.source || undefined,
    leadGenUse: 'High-signal personalization',
  }));

  const aiVars: CycleVariable[] = (doc.variableSchema?.aiGenerated || []).map(v => ({
    name: `{{${v.name}}}`,
    description: v.description || '',
    source: 'AI Generated',
  }));

  // Map email positions to unified emails (use recommended variant for each position)
  const emails: UnifiedEmail[] = doc.emailPositions.map((pos, idx) => {
    const recommendedVariant = pos.variants.find(v => v.isRecommended) || pos.variants[0];
    return {
      position: (idx + 1) as 1 | 2 | 3 | 4,
      title: pos.title || `Email ${idx + 1}`,
      waitDays: recommendedVariant?.waitDays || (idx === 0 ? 0 : 3),
      subjectLine: recommendedVariant?.subjectLine ?? undefined,  // Convert null to undefined
      emailBody: recommendedVariant?.emailBody || '',
      threadReply: recommendedVariant?.threadReply || false,
      wordCount: recommendedVariant?.wordCount,
      copyVariables: coreVars, // Copy variables apply to all emails
      score: recommendedVariant?.score,
    };
  });

  // Create a single campaign from the document
  const campaign: UnifiedCampaign = {
    id: doc.id,
    cycleId: doc.jobId,
    campaignNumber: 1,
    angle: 'custom_signal' as CampaignAngle, // Default angle
    documentName: doc.documentName,
    status: doc.status === 'approved' ? 'approved' :
            doc.status === 'denied' ? 'denied' : 'draft',
    campaignVariables: highSignalVars,
    emails,
    qaScoring: doc.qaScoring,
    createdAt: doc.createdAt,
    updatedAt: doc.updatedAt,
  };

  return {
    cycle: {
      id: doc.jobId,
      cycleNumber: 1,
      startDate: doc.createdAt,
      endDate: new Date(new Date(doc.createdAt).getTime() + 14 * 24 * 60 * 60 * 1000), // 14 days
      status: 'active',
    },
    config: {
      id: `config-${doc.id}`,
      cycleId: doc.jobId,
      icpMapping: doc.icpMapping || {
        targetIcp: { role: '', companyType: '', companySize: '' },
        painPoints: [],
        objections: [],
      },
      cycleVariables: [...highSignalVars, ...aiVars],
      strategicFocus: doc.objective || doc.vertical || 'Strategy generated from submission',
      targetOutcome: doc.strategyNotes?.callouts?.[0]?.text || 'Generate qualified meetings',
      createdAt: doc.createdAt,
      updatedAt: doc.updatedAt,
    },
    campaigns: [campaign],
  };
}

// Mock data for local testing
const MOCK_CYCLE_DATA: UnifiedCycleData = {
  cycle: {
    id: 'cycle-1',
    cycleNumber: 1,
    startDate: new Date('2025-02-01'),
    endDate: new Date('2025-02-14'),
    status: 'active',
  },
  config: {
    id: 'config-1',
    cycleId: 'cycle-1',
    icpMapping: {
      targetIcp: {
        role: 'VP Engineering / CTO',
        companyType: 'Mid-market SaaS companies',
        companySize: '50-500 employees',
      },
      painPoints: [
        {
          category: 'Technical',
          label: 'Legacy Systems',
          points: [
            'Stuck on aging core vendor infrastructure',
            'Technical debt slowing feature development',
            'Integration complexity with modern tools',
          ],
        },
        {
          category: 'Business',
          label: 'Growth Pressure',
          points: [
            'Need to scale without proportional headcount',
            'Competitive pressure from well-funded startups',
            'Board expectations for efficiency gains',
          ],
        },
      ],
      objections: [
        {
          objection: 'We already have a vendor for this',
          preemption: 'Acknowledge existing vendor, position as complementary enhancement',
        },
        {
          objection: 'Now is not a good time',
          preemption: 'Use timing as proof point - best ROI during planning cycles',
        },
        {
          objection: 'Too expensive',
          preemption: 'Lead with ROI case study showing 3x return',
        },
      ],
    },
    cycleVariables: [
      { name: '{{competitor}}', description: 'Primary competitor in their space', source: 'Onboarding form', leadGenUse: 'Filter by competitor usage' },
      { name: '{{industry_trend}}', description: 'Recent industry trend affecting their business', source: 'News monitoring', leadGenUse: 'Segment by industry vertical' },
      { name: '{{market_segment}}', description: 'Target market segment', source: 'Onboarding form', leadGenUse: 'Primary segmentation' },
    ],
    strategicFocus: 'Core vendor modernization and efficiency gains',
    targetOutcome: 'Book 15 qualified demos from VP Engineering / CTO prospects',
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  campaigns: [
    {
      id: 'campaign-1',
      cycleId: 'cycle-1',
      campaignNumber: 1,
      angle: 'custom_signal',
      documentName: 'Custom Signal - Hiring Trigger',
      status: 'spintaxed',
      campaignVariables: [
        { name: '{{job_posting_signal}}', description: 'Recent engineering job posting', source: 'LinkedIn Jobs' },
        { name: '{{hiring_role}}', description: 'Specific role being hired', source: 'Job posting' },
      ],
      emails: [
        { position: 1, title: 'Poke the Bear', waitDays: 0, subjectLine: 'Quick question about your {{hiring_role}} search', emailBody: 'Hi {{first_name}},\n\nNoticed you\'re hiring for {{hiring_role}} - typically means the backlog is growing faster than the team can handle.\n\n{{company_name}} might be interested in how {{case_study_company}} cleared 6 months of backlog in 3 weeks using our approach.\n\nWorth a quick chat?', threadReply: false, wordCount: 52, copyVariables: [{ name: '{{first_name}}', description: 'Contact first name' }, { name: '{{company_name}}', description: 'Company name' }], score: 87 },
        { position: 2, title: 'Creative Ideas', waitDays: 3, emailBody: 'A few ideas for {{company_name}}:\n\n1. {{creative_idea_1}}\n2. {{creative_idea_2}}\n3. {{creative_idea_3}}\n\nHappy to walk through any of these.', threadReply: true, wordCount: 35, copyVariables: [], score: 82 },
        { position: 3, title: 'Whole Offer', waitDays: 4, subjectLine: 'Results for {{industry}} companies like {{company_name}}', emailBody: 'Hi {{first_name}},\n\nCompanies in {{industry}} typically see:\n\n- 40% faster development cycles\n- 3x productivity per engineer\n- ROI within first quarter\n\n{{case_study_company}} achieved {{case_study_result}} - happy to share how.\n\n15 mins this week?', threadReply: false, wordCount: 48, copyVariables: [], score: 91 },
        { position: 4, title: 'Value Bomb', waitDays: 4, emailBody: 'Last thought - attached a quick analysis of {{company_name}}\'s public engineering footprint.\n\nNoticed a few opportunities. Let me know if helpful.', threadReply: true, wordCount: 28, copyVariables: [], score: 85 },
      ],
      spintaxedEmails: [
        { position: 1, title: 'Poke the Bear', waitDays: 0, subjectLine: 'Quick question about your {{hiring_role}} search', emailBody: '{Hi|Hello|Hey} {{first_name}},\n\n{Noticed|Saw|Just saw} you\'re hiring for {{hiring_role}} - {typically means|usually signals|often indicates} the backlog is growing faster than the team can handle.\n\n{{company_name}} might be interested in how {{case_study_company}} cleared 6 months of backlog in 3 weeks using our approach.\n\n{Worth a quick chat?|Open to a brief call?|Make sense to connect?}', threadReply: false, wordCount: 55, copyVariables: [{ name: '{{first_name}}', description: 'Contact first name' }, { name: '{{company_name}}', description: 'Company name' }], score: 87 },
        { position: 2, title: 'Creative Ideas', waitDays: 3, emailBody: '{A few ideas|Some thoughts|Quick ideas} for {{company_name}}:\n\n1. {{creative_idea_1}}\n2. {{creative_idea_2}}\n3. {{creative_idea_3}}\n\n{Happy to walk through any of these|Let me know if any resonate|Would love to discuss}.', threadReply: true, wordCount: 38, copyVariables: [], score: 82 },
        { position: 3, title: 'Whole Offer', waitDays: 4, subjectLine: 'Results for {{industry}} companies like {{company_name}}', emailBody: '{Hi|Hello} {{first_name}},\n\nCompanies in {{industry}} typically see:\n\n- 40% faster development cycles\n- 3x productivity per engineer\n- ROI within first quarter\n\n{{case_study_company}} achieved {{case_study_result}} - {happy to share how|would love to walk you through it|let me know if you\'d like the details}.\n\n{15 mins this week?|Quick call soon?|Time for a brief chat?}', threadReply: false, wordCount: 52, copyVariables: [], score: 91 },
        { position: 4, title: 'Value Bomb', waitDays: 4, emailBody: '{Last thought|One more thing|Final note} - attached a quick analysis of {{company_name}}\'s public engineering footprint.\n\n{Noticed a few opportunities|Spotted some interesting patterns|Found some potential wins}. {Let me know if helpful|Happy to discuss|Worth a look?}', threadReply: true, wordCount: 32, copyVariables: [], score: 85 },
      ],
      qaScoring: { overallScore: 87, verdict: 'Ship it', dimensions: [] },
      createdAt: new Date(),
      updatedAt: new Date(),
    },
    {
      id: 'campaign-2',
      cycleId: 'cycle-1',
      campaignNumber: 2,
      angle: 'persona_pain',
      documentName: 'Persona Pain - VP Eng Overwhelm',
      status: 'approved',
      campaignVariables: [
        { name: '{{persona_pain_point}}', description: 'Primary pain point for VP Eng persona', source: 'Persona research' },
      ],
      emails: [
        { position: 1, title: 'Pain Recognition', waitDays: 0, subjectLine: 'The {{persona_pain_point}} problem', emailBody: 'Hi {{first_name}},\n\nMost VP Engs I talk to mention {{persona_pain_point}} as their #1 challenge right now.\n\nIf that resonates, happy to share what {{case_study_company}} did about it.', threadReply: false, wordCount: 38, copyVariables: [], score: 84 },
        { position: 2, title: 'Social Proof', waitDays: 3, emailBody: 'Quick follow-up - {{case_study_company}} was dealing with the same issue.\n\nAfter implementing our approach: {{case_study_result}}.\n\nWorth 15 mins?', threadReply: true, wordCount: 28, copyVariables: [], score: 80 },
        { position: 3, title: 'Framework Share', waitDays: 4, subjectLine: 'Framework: Solving {{persona_pain_point}}', emailBody: 'Hi {{first_name}},\n\nPut together a quick framework for addressing {{persona_pain_point}}.\n\nNo sales pitch - just the approach that\'s worked for teams like yours.\n\nWant me to send it over?', threadReply: false, wordCount: 42, copyVariables: [], score: 86 },
        { position: 4, title: 'Breakup', waitDays: 4, emailBody: 'Closing the loop on this thread.\n\nIf {{persona_pain_point}} becomes a priority, I\'m here.\n\nBest,\n{{sender_first_name}}', threadReply: true, wordCount: 22, copyVariables: [], score: 78 },
      ],
      createdAt: new Date(),
      updatedAt: new Date(),
    },
    {
      id: 'campaign-3',
      cycleId: 'cycle-1',
      campaignNumber: 3,
      angle: 'case_study',
      documentName: 'Case Study - Regional Bank Success',
      status: 'draft',
      campaignVariables: [
        { name: '{{case_study_company}}', description: 'Featured case study company', value: 'Regional Bank X', source: 'Internal' },
        { name: '{{case_study_result}}', description: 'Key result from case study', value: '40% cost reduction in 6 months', source: 'Internal' },
      ],
      emails: [
        { position: 1, title: 'Results First', waitDays: 0, subjectLine: '{{case_study_result}} for {{industry}} company', emailBody: 'Hi {{first_name}},\n\n{{case_study_company}} achieved {{case_study_result}} using our approach.\n\nSimilar situation to {{company_name}} - worth sharing how they did it?', threadReply: false, wordCount: 32, copyVariables: [], score: 88 },
        { position: 2, title: 'Details', waitDays: 3, emailBody: 'More context on {{case_study_company}}:\n\n- Started: Legacy vendor dependency\n- Challenge: {{persona_pain_point}}\n- Result: {{case_study_result}}\n- Timeline: 6 months\n\nHappy to dive deeper.', threadReply: true, wordCount: 34, copyVariables: [], score: 85 },
        { position: 3, title: 'Comparison', waitDays: 4, subjectLine: '{{company_name}} vs {{case_study_company}} analysis', emailBody: 'Hi {{first_name}},\n\nPulled together a quick comparison of {{company_name}} and {{case_study_company}}\'s situations.\n\nSome interesting parallels. Want me to share?', threadReply: false, wordCount: 36, copyVariables: [], score: 83 },
        { position: 4, title: 'Final Offer', waitDays: 4, emailBody: 'Last note - if the {{case_study_result}} result is interesting, happy to set up a call with the {{case_study_company}} team to share their experience directly.\n\nLet me know.', threadReply: true, wordCount: 38, copyVariables: [], score: 82 },
      ],
      createdAt: new Date(),
      updatedAt: new Date(),
    },
    {
      id: 'campaign-4',
      cycleId: 'cycle-1',
      campaignNumber: 4,
      angle: 'risk_efficiency',
      documentName: 'Risk/Efficiency - Board Pressure',
      status: 'draft',
      campaignVariables: [
        { name: '{{efficiency_metric}}', description: 'Key efficiency metric', source: 'Industry benchmarks' },
      ],
      emails: [
        { position: 1, title: 'Risk Angle', waitDays: 0, subjectLine: 'Efficiency pressure at {{company_name}}?', emailBody: 'Hi {{first_name}},\n\nBoard pressure to do more with less is real right now.\n\nIf you\'re looking at {{efficiency_metric}} improvements, happy to share what\'s working for similar teams.', threadReply: false, wordCount: 38, copyVariables: [], score: 81 },
        { position: 2, title: 'Data Point', waitDays: 3, emailBody: 'Quick data point - teams using our approach see {{efficiency_metric}} improvements within 90 days.\n\nHappy to show you the math.', threadReply: true, wordCount: 26, copyVariables: [], score: 79 },
        { position: 3, title: 'ROI Framework', waitDays: 4, subjectLine: 'ROI calculator for {{company_name}}', emailBody: 'Hi {{first_name}},\n\nBuilt a quick ROI model based on {{company_name}}\'s public data.\n\nShows potential for {{efficiency_metric}} gains. Want me to walk you through it?', threadReply: false, wordCount: 38, copyVariables: [], score: 84 },
        { position: 4, title: 'Final Touch', waitDays: 4, emailBody: 'Closing the loop.\n\nIf efficiency becomes a priority, the offer stands - happy to share the ROI model anytime.\n\nBest,\n{{sender_first_name}}', threadReply: true, wordCount: 28, copyVariables: [], score: 77 },
      ],
      createdAt: new Date(),
      updatedAt: new Date(),
    },
  ],
};

export function UnifiedCycleView({ clientId, cycleId, className }: UnifiedCycleViewProps) {
  // State for collapsible sections
  const [icpOpen, setIcpOpen] = useState(true);
  const [variablesOpen, setVariablesOpen] = useState(true);

  // Regeneration modal state
  const [regeneration, setRegeneration] = useState<RegenerationState | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);

  // Approval state
  const [approvingCampaignId, setApprovingCampaignId] = useState<string | null>(null);

  // Spintax state
  const [spintaxingCampaignId, setSpintaxingCampaignId] = useState<string | null>(null);

  // Push to EmailBison state
  const [pushingCampaignId, setPushingCampaignId] = useState<string | null>(null);

  // Campaign data state (for updates after approval/spintax)
  const [localCampaigns, setLocalCampaigns] = useState<UnifiedCampaign[] | null>(null);

  // API data state
  const [apiData, setApiData] = useState<UnifiedCycleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [useMockData, setUseMockData] = useState(false);

  // Fetch cycle data from API, falling back to documents if no cycles exist
  useEffect(() => {
    async function fetchCycleData() {
      try {
        setLoading(true);
        setError(null);

        // First try the unified cycle endpoint
        try {
          const response = await unifiedCycleApi.getUnifiedCycle(clientId, cycleId);
          if (response.data?.cycle) {
            setApiData(response.data);
            setUseMockData(false);
            return;
          }
        } catch {
          // Cycle endpoint failed, try documents
          console.log('No cycles found, trying documents API...');
        }

        // Fallback: Try to get documents and transform them
        try {
          const docsResponse = await campaignDocumentApi.getClientDocuments(clientId);
          if (docsResponse.documents && docsResponse.documents.length > 0) {
            // Use the most recent document
            const latestDoc = docsResponse.documents[0];
            const transformedData = transformDocumentToCycleData(latestDoc);
            setApiData(transformedData);
            setUseMockData(false);
            console.log('Loaded data from campaign document:', latestDoc.documentName);
            return;
          }
        } catch (docErr) {
          console.warn('Documents API also failed:', docErr);
        }

        // No data available, use mock data
        setUseMockData(true);
      } catch (err) {
        console.warn('All APIs failed, using mock data:', err);
        setUseMockData(true);
      } finally {
        setLoading(false);
      }
    }

    fetchCycleData();
  }, [clientId, cycleId]);

  // Use API data or fallback to mock data
  const baseCycleData = useMockData ? MOCK_CYCLE_DATA : apiData;

  // Use local campaigns if updated, otherwise use base data
  const cycleData = baseCycleData ? {
    ...baseCycleData,
    campaigns: localCampaigns || baseCycleData.campaigns,
  } : null;

  // Collect all variables for lead gen export
  const allVariables = useMemo(() => {
    if (!cycleData) return { cycle: [], campaign: [], copy: [] };

    const cycle = cycleData.config.cycleVariables || [];
    const campaign: CycleVariable[] = [];
    const copy: CycleVariable[] = [];

    cycleData.campaigns.forEach(c => {
      campaign.push(...(c.campaignVariables || []));
      c.emails.forEach(e => {
        copy.push(...(e.copyVariables || []));
      });
    });

    return { cycle, campaign, copy };
  }, [cycleData]);

  // Open regeneration modal with appropriate config
  const openRegenerationModal = useCallback((
    section: RegenerationSection,
    config: RegenerationModalConfig,
    subSection?: ICPSubSection,
    scope?: RegenerationScope
  ) => {
    setRegeneration({ isOpen: true, config, section, subSection, scope });
  }, []);

  // Handle regeneration submit
  const handleRegenerationSubmit = useCallback(async (
    instruction: string,
    selectedScope?: string,
    preserveExisting?: boolean
  ) => {
    if (!regeneration || !cycleData) return;

    setIsRegenerating(true);
    try {
      // Build the request
      const request = {
        section: regeneration.section,
        subSection: regeneration.subSection,
        scope: regeneration.scope,
        instruction,
        preserveExisting,
      };

      // Call API (will 404 with mock data, but shows the flow)
      await unifiedCycleApi.regenerateSection(cycleData.cycle.id, request);

      toast.success(`Revision requested for ${regeneration.config.title.replace('Request Revision for ', '')}`);
      setRegeneration(null);
    } catch (error) {
      // For mock data, just show success anyway
      toast.success(`Revision requested (mock mode)`);
      setRegeneration(null);
    } finally {
      setIsRegenerating(false);
    }
  }, [regeneration, cycleData]);

  // Handler generators for each section
  const handleRequestRevisionCampaign = useCallback((campaignNumber: 1 | 2 | 3 | 4) => {
    const campaign = cycleData?.campaigns.find(c => c.campaignNumber === campaignNumber);
    openRegenerationModal('campaign', {
      title: `Request Revision for Campaign ${campaignNumber}`,
      description: `Request revision for all 4 emails in the ${campaign?.documentName || 'campaign'}.`,
      placeholder: 'E.g., Make the tone more casual, focus more on ROI, add stronger CTAs...',
      scopeOptions: [
        { value: 'all', label: 'All 4 emails', description: 'Request revision for entire email sequence' },
        { value: 'opener', label: 'Just email 1', description: 'Only regenerate the opening email' },
      ],
    }, undefined, { campaignNumber });
  }, [cycleData, openRegenerationModal]);

  const handleRequestRevisionEmail = useCallback((campaignNumber: 1 | 2 | 3 | 4, position: 1 | 2 | 3 | 4) => {
    const campaign = cycleData?.campaigns.find(c => c.campaignNumber === campaignNumber);
    const email = campaign?.emails.find(e => e.position === position);
    openRegenerationModal('email', {
      title: `Request Revision for Email ${position}`,
      description: `Update "${email?.title || 'this email'}" in ${campaign?.documentName || 'the campaign'}.`,
      placeholder: 'E.g., Make it shorter, add a specific case study, change the CTA...',
      currentContent: email ? `Subject: ${email.subjectLine || '(threaded)'}\n\n${email.emailBody}` : undefined,
    }, undefined, { campaignNumber, emailPosition: position });
  }, [cycleData, openRegenerationModal]);

  // Helper to update campaign status locally
  const updateCampaignStatus = useCallback((campaignId: string, newStatus: CampaignStatus) => {
    setLocalCampaigns(prev => {
      const campaigns = prev || cycleData?.campaigns || [];
      return campaigns.map(c => c.id === campaignId ? { ...c, status: newStatus } : c);
    });
  }, [cycleData?.campaigns]);

  // Approval handlers - cast strategyApi through unknown to access reviewDocument method
  type ReviewDocumentApi = { reviewDocument: (id: string, action: string, comment?: string) => Promise<unknown> };

  const handleApprove = useCallback(async (campaignId: string) => {
    setApprovingCampaignId(campaignId);
    try {
      await (strategyApi as unknown as ReviewDocumentApi).reviewDocument(campaignId, 'approve');
      updateCampaignStatus(campaignId, 'approved');
      toast.success('Campaign approved! Ready for spintax.');
    } catch (error) {
      // For mock mode, still update locally
      updateCampaignStatus(campaignId, 'approved');
      toast.success('Campaign approved! (mock mode)');
    } finally {
      setApprovingCampaignId(null);
    }
  }, [updateCampaignStatus]);

  const handleDeny = useCallback(async (campaignId: string) => {
    setApprovingCampaignId(campaignId);
    try {
      await (strategyApi as unknown as ReviewDocumentApi).reviewDocument(campaignId, 'deny');
      updateCampaignStatus(campaignId, 'denied');
      toast.info('Campaign denied.');
    } catch (error) {
      updateCampaignStatus(campaignId, 'denied');
      toast.info('Campaign denied. (mock mode)');
    } finally {
      setApprovingCampaignId(null);
    }
  }, [updateCampaignStatus]);

  const handleRequestRevision = useCallback(async (campaignId: string, comment?: string) => {
    setApprovingCampaignId(campaignId);
    try {
      await (strategyApi as unknown as ReviewDocumentApi).reviewDocument(campaignId, 'revision_requested', comment);
      updateCampaignStatus(campaignId, 'revision_requested');
      toast.info('Revision requested. A new generation will be triggered.');
    } catch (error) {
      updateCampaignStatus(campaignId, 'revision_requested');
      toast.info('Revision requested. (mock mode)');
    } finally {
      setApprovingCampaignId(null);
    }
  }, [updateCampaignStatus]);

  // Spintax handler - uses new campaign documents API
  const handleTriggerSpintax = useCallback(async (campaignId: string) => {
    setSpintaxingCampaignId(campaignId);
    updateCampaignStatus(campaignId, 'spintax_pending');

    try {
      // Use new campaign document spintax endpoint
      const response = await campaignDocumentApi.addSpintax(campaignId);
      if (response.status === 'spintaxed') {
        updateCampaignStatus(campaignId, 'spintaxed');
        toast.success('Spintax complete! Ready to push to EmailBison.');
      }
    } catch (error) {
      console.error('Spintax error:', error);
      // Revert to approved status on error
      updateCampaignStatus(campaignId, 'approved');
      toast.error('Spintax failed. Please try again.');
    } finally {
      setSpintaxingCampaignId(null);
    }
  }, [updateCampaignStatus]);

  // Push to EmailBison handler - uses new campaign documents API
  const handlePushToEmailBison = useCallback(async (campaignId: string) => {
    setPushingCampaignId(campaignId);
    try {
      // Use new campaign document push endpoint
      const response = await campaignDocumentApi.pushToEmailBison(campaignId);
      updateCampaignStatus(campaignId, 'sent');
      toast.success(`Campaign pushed to EmailBison! ${response.emailsPushed} emails created.`);
    } catch (error) {
      console.error('Push to EmailBison error:', error);
      toast.error('Failed to push to EmailBison. Please try again.');
    } finally {
      setPushingCampaignId(null);
    }
  }, [updateCampaignStatus]);

  if (loading) {
    return (
      <Card className={cn('animate-pulse', className)}>
        <CardContent className="p-6">
          <div className="h-8 bg-muted rounded w-1/3 mb-4" />
          <div className="h-32 bg-muted rounded" />
        </CardContent>
      </Card>
    );
  }

  if (!cycleData) {
    return (
      <Card className={cn(className)}>
        <CardContent className="p-6 text-center text-muted-foreground">
          No cycle data available. Generate a new strategy to get started.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Mock Data Indicator */}
      {useMockData && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
          <span className="font-medium">Preview Mode:</span>
          <span>Showing sample data. Generate a strategy to see real cycle data.</span>
        </div>
      )}

      {/* Cycle Header */}
      <CycleHeader
        cycleNumber={cycleData.cycle.cycleNumber}
        startDate={cycleData.cycle.startDate}
        endDate={cycleData.cycle.endDate}
        status={cycleData.cycle.status}
        strategicFocus={cycleData.config.strategicFocus}
        targetOutcome={cycleData.config.targetOutcome}
      />

      {/* Cycle Variables Panel */}
      <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
        <Card>
          <CollapsibleTrigger asChild>
            <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors">
              <div className="flex items-center gap-2">
                <Variable className="h-5 w-5 text-purple-600" />
                <span className="font-semibold">Cycle Variables</span>
                <span className="text-sm text-muted-foreground">
                  ({allVariables.cycle.length} cycle, {allVariables.campaign.length} campaign, {allVariables.copy.length} copy)
                </span>
              </div>
              <ChevronDown className={cn('h-5 w-5 transition-transform', variablesOpen && 'rotate-180')} />
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="pt-0">
              <CycleVariablesPanel
                cycleVariables={allVariables.cycle}
                campaignVariables={allVariables.campaign}
                copyVariables={allVariables.copy}
              />
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* ICP Mapping */}
      {cycleData.config.icpMapping && (
        <Collapsible open={icpOpen} onOpenChange={setIcpOpen}>
          <Card>
            <CollapsibleTrigger asChild>
              <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-2">
                  <Target className="h-5 w-5 text-blue-600" />
                  <span className="font-semibold">ICP & Objection Mapping</span>
                </div>
                <ChevronDown className={cn('h-5 w-5 transition-transform', icpOpen && 'rotate-180')} />
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="pt-0">
                <ICPMappingSection
                  icpMapping={cycleData.config.icpMapping}
                />
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      )}

      {/* Campaign Grid (4 campaigns) */}
      <CampaignGrid
        campaigns={cycleData.campaigns}
        onRequestRevisionCampaign={handleRequestRevisionCampaign}
        onRequestRevisionEmail={handleRequestRevisionEmail}
        onApprove={handleApprove}
        onDeny={handleDeny}
        onRequestRevision={handleRequestRevision}
        approvingCampaignId={approvingCampaignId || undefined}
        onTriggerSpintax={handleTriggerSpintax}
        spintaxingCampaignId={spintaxingCampaignId || undefined}
        onPushToEmailBison={handlePushToEmailBison}
        pushingCampaignId={pushingCampaignId || undefined}
      />

      {/* Regeneration Modal */}
      {regeneration && (
        <RegenerationModal
          isOpen={regeneration.isOpen}
          onClose={() => setRegeneration(null)}
          onSubmit={handleRegenerationSubmit}
          config={regeneration.config}
          isSubmitting={isRegenerating}
        />
      )}
    </div>
  );
}
