import type {
  Client,
  Domain,
  Inbox,
  CampaignIdea,
  Campaign,
  Lead,
} from '@/lib/types';

// Helper to create dates in the past
const daysAgo = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date;
};

// ============ CLIENTS ============
export const mockClients: Client[] = [
  {
    id: 'client-1',
    name: 'TechFlow Solutions',
    domain: 'techflow.io',
    onboardingComplete: true,
    onboardingData: {
      contactFirstNames: ['Sarah', 'Mike', 'Jordan'],
      primaryDomain: 'techflow.io',
      industry: 'SaaS',
      product: 'Project management software for remote teams. We help distributed teams stay aligned with async-first collaboration tools.',
      inboxesNeeded: 10,
      notes: 'Focus on Series A-C startups in the tech space.',
    },
    createdAt: daysAgo(45),
  },
  {
    id: 'client-2',
    name: 'GrowthMetrics',
    domain: 'growthmetrics.co',
    onboardingComplete: true,
    onboardingData: {
      contactFirstNames: ['Alex', 'Casey'],
      primaryDomain: 'growthmetrics.co',
      industry: 'Marketing Agency',
      product: 'Full-service B2B marketing agency specializing in demand generation and account-based marketing.',
      inboxesNeeded: 8,
    },
    createdAt: daysAgo(30),
  },
  {
    id: 'client-3',
    name: 'FinanceHub Pro',
    domain: 'financehubpro.com',
    onboardingComplete: false,
    createdAt: daysAgo(2),
  },
  {
    id: 'client-4',
    name: 'CloudScale Inc',
    domain: 'cloudscale.dev',
    onboardingComplete: true,
    onboardingData: {
      contactFirstNames: ['David', 'Emma', 'Chris', 'Lisa'],
      primaryDomain: 'cloudscale.dev',
      industry: 'Technology',
      product: 'Cloud infrastructure optimization platform. We help companies reduce their AWS/GCP bills by 30-50% through intelligent resource management.',
      inboxesNeeded: 12,
      notes: 'Target companies spending $50k+/month on cloud.',
    },
    createdAt: daysAgo(15),
  },
];

// ============ DOMAINS ============
export const mockDomains: Domain[] = [
  // TechFlow domains - mix of active, warming, pending, and rejected
  { id: 'domain-1', clientId: 'client-1', domain: 'techflow.io', status: 'active', healthScore: 92, createdAt: daysAgo(40) },
  { id: 'domain-2', clientId: 'client-1', domain: 'techflow-mail.com', status: 'warming', healthScore: 78, createdAt: daysAgo(20) },
  { id: 'domain-3', clientId: 'client-1', domain: 'tf-outreach.com', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-3a', clientId: 'client-1', domain: 'mail-techflow.io', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-3b', clientId: 'client-1', domain: 'go-techflow.io', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-3c', clientId: 'client-1', domain: 'techflow-hq.com', status: 'rejected', createdAt: daysAgo(2) },
  // GrowthMetrics domains
  { id: 'domain-4', clientId: 'client-2', domain: 'growthmetrics.co', status: 'active', healthScore: 88, createdAt: daysAgo(28) },
  { id: 'domain-5', clientId: 'client-2', domain: 'gm-connect.io', status: 'active', healthScore: 85, createdAt: daysAgo(25) },
  { id: 'domain-5a', clientId: 'client-2', domain: 'mail-growthmetrics.co', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-5b', clientId: 'client-2', domain: 'gm-outbound.io', status: 'rejected', createdAt: daysAgo(3) },
  // CloudScale domains
  { id: 'domain-6', clientId: 'client-4', domain: 'cloudscale.dev', status: 'active', healthScore: 95, createdAt: daysAgo(14) },
  { id: 'domain-7', clientId: 'client-4', domain: 'cs-reach.com', status: 'warming', healthScore: 65, createdAt: daysAgo(7) },
  { id: 'domain-7a', clientId: 'client-4', domain: 'mail-cloudscale.dev', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-7b', clientId: 'client-4', domain: 'try-cloudscale.io', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'domain-7c', clientId: 'client-4', domain: 'cloudscale-app.com', status: 'pending_approval', createdAt: daysAgo(1) },
];

// ============ INBOXES ============
export const mockInboxes: Inbox[] = [
  // TechFlow inboxes - mix of active, warming, pending, and rejected
  { id: 'inbox-1', clientId: 'client-1', domainId: 'domain-1', email: 'sarah@techflow.io', firstName: 'Sarah', lastName: 'Chen', status: 'active', dailySendLimit: 50, createdAt: daysAgo(38) },
  { id: 'inbox-2', clientId: 'client-1', domainId: 'domain-1', email: 'mike@techflow.io', firstName: 'Mike', lastName: 'Johnson', status: 'active', dailySendLimit: 50, createdAt: daysAgo(38) },
  { id: 'inbox-3', clientId: 'client-1', domainId: 'domain-1', email: 'jordan@techflow.io', firstName: 'Jordan', lastName: 'Smith', status: 'active', dailySendLimit: 45, createdAt: daysAgo(35) },
  { id: 'inbox-4', clientId: 'client-1', domainId: 'domain-2', email: 'sarah@techflow-mail.com', firstName: 'Sarah', lastName: 'Chen', status: 'warming', warmupProgress: 65, createdAt: daysAgo(18) },
  { id: 'inbox-5', clientId: 'client-1', domainId: 'domain-2', email: 'mike@techflow-mail.com', firstName: 'Mike', lastName: 'Johnson', status: 'warming', warmupProgress: 58, createdAt: daysAgo(18) },
  { id: 'inbox-6', clientId: 'client-1', domainId: 'domain-1', email: 'sarah.chen@techflow.io', firstName: 'Sarah', lastName: 'Chen', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-6a', clientId: 'client-1', domainId: 'domain-1', email: 'mike.j@techflow.io', firstName: 'Mike', lastName: 'Johnson', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-6b', clientId: 'client-1', domainId: 'domain-1', email: 'j.smith@techflow.io', firstName: 'Jordan', lastName: 'Smith', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-6c', clientId: 'client-1', domainId: 'domain-1', email: 'team@techflow.io', firstName: 'Team', lastName: 'TechFlow', status: 'rejected', createdAt: daysAgo(2) },
  { id: 'inbox-6d', clientId: 'client-1', domainId: 'domain-2', email: 'jordan@techflow-mail.com', firstName: 'Jordan', lastName: 'Smith', status: 'pending_approval', createdAt: daysAgo(1) },
  // GrowthMetrics inboxes
  { id: 'inbox-7', clientId: 'client-2', domainId: 'domain-4', email: 'alex@growthmetrics.co', firstName: 'Alex', lastName: 'Rivera', status: 'active', dailySendLimit: 50, createdAt: daysAgo(26) },
  { id: 'inbox-8', clientId: 'client-2', domainId: 'domain-4', email: 'casey@growthmetrics.co', firstName: 'Casey', lastName: 'Morgan', status: 'active', dailySendLimit: 50, createdAt: daysAgo(26) },
  { id: 'inbox-9', clientId: 'client-2', domainId: 'domain-5', email: 'alex@gm-connect.io', firstName: 'Alex', lastName: 'Rivera', status: 'active', dailySendLimit: 40, createdAt: daysAgo(23) },
  { id: 'inbox-10', clientId: 'client-2', domainId: 'domain-5', email: 'casey@gm-connect.io', firstName: 'Casey', lastName: 'Morgan', status: 'warming', warmupProgress: 82, createdAt: daysAgo(10) },
  { id: 'inbox-10a', clientId: 'client-2', domainId: 'domain-4', email: 'alex.r@growthmetrics.co', firstName: 'Alex', lastName: 'Rivera', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-10b', clientId: 'client-2', domainId: 'domain-4', email: 'casey.m@growthmetrics.co', firstName: 'Casey', lastName: 'Morgan', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-10c', clientId: 'client-2', domainId: 'domain-5', email: 'sales@gm-connect.io', firstName: 'Sales', lastName: 'Team', status: 'rejected', createdAt: daysAgo(3) },
  // CloudScale inboxes
  { id: 'inbox-11', clientId: 'client-4', domainId: 'domain-6', email: 'david@cloudscale.dev', firstName: 'David', lastName: 'Park', status: 'active', dailySendLimit: 50, createdAt: daysAgo(12) },
  { id: 'inbox-12', clientId: 'client-4', domainId: 'domain-6', email: 'emma@cloudscale.dev', firstName: 'Emma', lastName: 'Wilson', status: 'active', dailySendLimit: 50, createdAt: daysAgo(12) },
  { id: 'inbox-13', clientId: 'client-4', domainId: 'domain-7', email: 'chris@cs-reach.com', firstName: 'Chris', lastName: 'Taylor', status: 'warming', warmupProgress: 35, createdAt: daysAgo(5) },
  { id: 'inbox-14', clientId: 'client-4', domainId: 'domain-7', email: 'lisa@cs-reach.com', firstName: 'Lisa', lastName: 'Brown', status: 'pending_approval', createdAt: daysAgo(2) },
  { id: 'inbox-14a', clientId: 'client-4', domainId: 'domain-6', email: 'david.p@cloudscale.dev', firstName: 'David', lastName: 'Park', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-14b', clientId: 'client-4', domainId: 'domain-6', email: 'emma.w@cloudscale.dev', firstName: 'Emma', lastName: 'Wilson', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-14c', clientId: 'client-4', domainId: 'domain-6', email: 'chris.t@cloudscale.dev', firstName: 'Chris', lastName: 'Taylor', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-14d', clientId: 'client-4', domainId: 'domain-6', email: 'lisa.b@cloudscale.dev', firstName: 'Lisa', lastName: 'Brown', status: 'pending_approval', createdAt: daysAgo(1) },
  { id: 'inbox-14e', clientId: 'client-4', domainId: 'domain-7', email: 'info@cs-reach.com', firstName: 'Info', lastName: 'CloudScale', status: 'rejected', createdAt: daysAgo(3) },
];

// ============ CAMPAIGN IDEAS ============
export const mockCampaignIdeas: CampaignIdea[] = [
  // TechFlow ideas - Full data structure
  {
    id: 'idea-1',
    clientId: 'client-1',
    industry: 'SaaS',
    segment: 'Series A Startups',
    title: 'Remote Team Pain Points',
    angle: 'Address the communication gaps that plague distributed teams. Lead with the cost of misalignment and position your tool as the solution.',
    campaignType: 'custom_signal',
    icpDescription: 'Engineering managers and VPs at Series A startups (50-200 employees) managing distributed teams across 3+ time zones.',
    objections: ['We already use Slack', 'Too many tools already', 'Need buy-in from team'],
    valueProposition: {
      business: 'Reduce meeting time by 40% while improving team alignment scores',
      personal: 'Stop playing calendar Tetris and get your evenings back',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}', roleTitle: '{{role_title}}' },
      highSignal: { tenureYears: '{{tenure_years}}', hiringRoles: '{{hiring_roles}}' },
      aiGenerated: { customerType: 'distributed engineering teams' },
      caseStudy: { company: 'Acme Corp', result: '42% fewer meetings', metric: 'meeting hours', timeframe: '3 months' },
    },
    email1: {
      subject: 'Quick question',
      body: '{{first_name}} – saw you\'re hiring {{hiring_roles}} at {{company_name}}.\n\nGrowing distributed teams usually means more syncs, more Slack chaos, and more "can we find a time that works for everyone?"\n\nWe helped Acme Corp cut meeting time by 42% while actually improving their sprint velocity.\n\nWorth a quick look?',
      cta: 'Worth a quick look?',
    },
    followUps: [
      { day: 3, copy: { subject: '', body: 'Bumping this up—any interest in seeing how Acme did it?', cta: 'Happy to share the case study.' }, angle: 'Case study offer' },
      { day: 7, copy: { subject: 'Ideas for {{company_name}}', body: 'Had a few specific ideas...', cta: 'Worth a 15-min call?' }, angle: 'Creative ideas' },
      { day: 11, copy: { subject: 'Last one from me', body: 'Closing the loop—if this isn\'t a priority right now, totally get it.', cta: 'Let me know if timing is better in Q2.' }, angle: 'Breakup' },
    ],
    qaScore: { total: 88, situationRecognition: 23, valueClarity: 22, personalizationQuality: 18, ctaEffort: 13, length: 8, subjectLine: 4 },
    status: 'approved',
    generatedAt: daysAgo(35),
  },
  {
    id: 'idea-2',
    clientId: 'client-1',
    industry: 'SaaS',
    segment: 'Series B Startups',
    title: 'Productivity Benchmark',
    angle: 'Share data on how top-performing remote teams operate. Create urgency around falling behind competitors.',
    campaignType: 'whole_offer',
    icpDescription: 'COOs and Heads of Operations at Series B startups scaling from 100-500 employees.',
    valueProposition: {
      business: 'Hit growth targets without proportionally growing headcount',
      personal: 'Prove to the board that ops is a competitive advantage, not overhead',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      aiGenerated: { customerDescription: 'fast-growing SaaS teams' },
    },
    email1: {
      subject: 'Productivity data',
      body: '{{first_name}} – we surveyed 500+ remote-first companies last quarter.\n\nTop 10% performers share three practices that others don\'t.\n\nWould it be useful if I sent over the benchmarks?',
      cta: 'Would it be useful if I sent over the benchmarks?',
    },
    qaScore: { total: 82, situationRecognition: 20, valueClarity: 21, personalizationQuality: 16, ctaEffort: 14, length: 7, subjectLine: 4 },
    status: 'approved',
    generatedAt: daysAgo(30),
  },
  {
    id: 'idea-3',
    clientId: 'client-1',
    industry: 'SaaS',
    segment: 'Tech Companies',
    title: 'Async-First Revolution',
    angle: 'Challenge the meeting-heavy culture. Position async collaboration as the future of productive work.',
    campaignType: 'creative_ideas',
    constraintBox: ['Async video messaging', 'Threaded discussions', 'Project timelines', 'Status updates'],
    icpDescription: 'Engineering Directors at tech companies with 200+ employees and heavy meeting culture.',
    objections: ['Culture won\'t change', 'Executives need meetings', 'Already tried async'],
    valueProposition: {
      business: 'Reclaim 8+ hours per week of engineering time for actual building',
      personal: 'Be the leader who fixed the meeting problem',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: { recentPostTopic: 'remote work challenges', competitor: 'Loom' },
    },
    email1: {
      subject: 'Ideas for {{company_name}}',
      body: '{{first_name}} – I was back on your site and had some ideas for reducing meeting load at {{company_name}}.',
      cta: 'If interesting, could hop on a call to share what\'s working.',
    },
    creativeIdeas: [
      { feature: 'Async video messaging', action: 'Replace standup meetings', target: 'engineering teams', benefit: 'recovers 5 hrs/week without losing context' },
      { feature: 'Threaded discussions', action: 'Move brainstorms async', target: 'product planning', benefit: 'better ideas from introverts, documented decisions' },
      { feature: 'Status updates', action: 'Automate progress reports', target: 'stakeholder updates', benefit: 'no more "can you send me an update" pings' },
    ],
    qaScore: { total: 91, situationRecognition: 24, valueClarity: 23, personalizationQuality: 19, ctaEffort: 13, length: 8, subjectLine: 4 },
    status: 'pending',
    generatedAt: daysAgo(5),
  },
  {
    id: 'idea-4',
    clientId: 'client-1',
    industry: 'SaaS',
    segment: 'Remote-First Companies',
    title: 'Tool Consolidation',
    angle: 'Highlight the cost and friction of using multiple disconnected tools. Offer a unified alternative.',
    campaignType: 'custom_signal',
    icpDescription: 'IT Directors at remote-first companies with 5+ collaboration tools in their stack.',
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: { stackCrm: 'Salesforce', competitor: 'Monday.com' },
      custom: { toolCount: '7 collaboration tools' },
    },
    email1: {
      subject: 'Quick question',
      body: '{{first_name}} – noticed {{company_name}} is using {{toolCount}} for collaboration.\n\nHow are you handling the context-switching tax?',
      cta: 'Curious—is consolidation on the roadmap?',
    },
    qaScore: { total: 79, situationRecognition: 21, valueClarity: 18, personalizationQuality: 17, ctaEffort: 12, length: 7, subjectLine: 4 },
    status: 'pending',
    generatedAt: daysAgo(5),
  },
  // GrowthMetrics ideas
  {
    id: 'idea-5',
    clientId: 'client-2',
    industry: 'Marketing Agency',
    segment: 'B2B Tech',
    title: 'ABM Success Stories',
    angle: 'Lead with case studies of similar companies achieving 3x pipeline growth. Tease the strategy without revealing all.',
    campaignType: 'custom_signal',
    icpDescription: 'VP Marketing at B2B tech companies ($10M-$100M ARR) with sales cycles 3+ months.',
    objections: ['ABM is expensive', 'Tried it before', 'Need more headcount first'],
    valueProposition: {
      business: 'Generate 3x pipeline from target accounts without 3x budget',
      personal: 'Hit pipeline targets and make the CMO look like a genius',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: { competitor: 'HubSpot', pressHeadline: 'Series B funding' },
      caseStudy: { company: 'TechVenture', result: '3.2x pipeline growth', metric: 'pipeline', timeframe: '6 months' },
    },
    email1: {
      subject: 'ABM case study',
      body: '{{first_name}} – congrats on the {{pressHeadline}}.\n\nWith fresh funding, I\'m guessing pipeline growth is top of mind.\n\nWe helped TechVenture hit 3.2x pipeline growth in 6 months using a targeted ABM approach.\n\nWorth a look at how they did it?',
      cta: 'Worth a look at how they did it?',
    },
    qaScore: { total: 86, situationRecognition: 22, valueClarity: 23, personalizationQuality: 17, ctaEffort: 13, length: 7, subjectLine: 4 },
    status: 'approved',
    generatedAt: daysAgo(25),
  },
  {
    id: 'idea-6',
    clientId: 'client-2',
    industry: 'Marketing Agency',
    segment: 'SaaS Companies',
    title: 'Marketing Efficiency',
    angle: 'Address the common problem of high CAC. Position your agency as the solution to more efficient growth.',
    campaignType: 'whole_offer',
    icpDescription: 'CMOs at SaaS companies spending $500k+/year on marketing with CAC:LTV concerns.',
    valueProposition: {
      business: 'Reduce CAC by 30% while maintaining growth rate',
      personal: 'Stop defending marketing spend at every board meeting',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
    },
    email1: {
      subject: 'CAC question',
      body: '{{first_name}} – is your CAC where you want it?\n\nMost SaaS companies we talk to are seeing 20-40% higher acquisition costs than 2 years ago.\n\nWe specialize in finding the efficiency gaps.',
      cta: 'Is this a priority right now?',
    },
    qaScore: { total: 76, situationRecognition: 18, valueClarity: 20, personalizationQuality: 15, ctaEffort: 12, length: 7, subjectLine: 4 },
    status: 'pending',
    generatedAt: daysAgo(8),
  },
  {
    id: 'idea-7',
    clientId: 'client-2',
    industry: 'Marketing Agency',
    segment: 'Series B+',
    title: 'Board-Ready Metrics',
    angle: 'Help marketing leaders look good to their board with impressive, defensible metrics.',
    campaignType: 'fallback',
    icpDescription: 'Marketing leaders at VC-backed companies preparing for board presentations.',
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      custom: { employee1: '{{marketing_director}}', employee2: '{{demand_gen_lead}}' },
    },
    email1: {
      subject: 'Quick question',
      body: '{{first_name}} – not sure if you\'re the right person for this.\n\nWe help marketing teams build board-ready attribution models.\n\nLet me know if {{marketing_director}} or {{demand_gen_lead}} would be better to connect with.',
      cta: 'Let me know if {{marketing_director}} or {{demand_gen_lead}} would be better.',
    },
    qaScore: { total: 68, situationRecognition: 15, valueClarity: 17, personalizationQuality: 14, ctaEffort: 11, length: 7, subjectLine: 4 },
    status: 'rejected',
    generatedAt: daysAgo(8),
  },
  // CloudScale ideas
  {
    id: 'idea-8',
    clientId: 'client-4',
    industry: 'Technology',
    segment: 'High Cloud Spend',
    title: 'Cloud Cost Shock',
    angle: 'Lead with the surprising statistic that most companies overspend on cloud by 30-40%. Offer a free audit.',
    campaignType: 'custom_signal',
    icpDescription: 'VP Infrastructure at companies spending $50k+/month on AWS/GCP/Azure.',
    objections: ['Already optimized', 'Don\'t have time', 'Security concerns'],
    valueProposition: {
      business: 'Cut cloud spend by 30-50% without performance impact',
      personal: 'Be the hero who found $500k in annual savings',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: { hiringRoles: 'DevOps engineers' },
      custom: { cloudProvider: 'AWS', estimatedSpend: '$80k/month' },
    },
    email1: {
      subject: 'AWS spend',
      body: '{{first_name}} – saw you\'re hiring {{hiringRoles}}.\n\nBefore you add headcount to manage your {{cloudProvider}} infrastructure, have you looked at what you\'re overpaying?\n\nMost companies at your scale leave 30-40% on the table.\n\nWorth a free audit to see where you stand?',
      cta: 'Worth a free audit to see where you stand?',
    },
    followUps: [
      { day: 4, copy: { subject: '', body: 'Bumping this—quick 15-min audit call could save you $20k/month.', cta: 'Interested?' }, angle: 'ROI focus' },
      { day: 8, copy: { subject: 'Cloud optimization ideas', body: 'Had 3 specific ideas for {{company_name}}...', cta: 'Worth a look?' }, angle: 'Creative ideas' },
    ],
    qaScore: { total: 89, situationRecognition: 23, valueClarity: 24, personalizationQuality: 18, ctaEffort: 13, length: 7, subjectLine: 4 },
    status: 'approved',
    generatedAt: daysAgo(10),
  },
  {
    id: 'idea-9',
    clientId: 'client-4',
    industry: 'Technology',
    segment: 'Engineering Leaders',
    title: 'DevOps Efficiency',
    angle: 'Position cloud optimization as freeing up engineering resources for what matters - building product.',
    campaignType: 'creative_ideas',
    constraintBox: ['Resource right-sizing', 'Spot instance automation', 'Reserved capacity planning', 'Cost anomaly detection'],
    icpDescription: 'Engineering VPs at tech companies with 20+ engineers and growing infrastructure complexity.',
    valueProposition: {
      business: 'Free up 2 FTE worth of DevOps time for product work',
      personal: 'Stop firefighting infrastructure and ship more features',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      highSignal: { recentPostTopic: 'scaling challenges' },
    },
    email1: {
      subject: 'DevOps bandwidth',
      body: '{{first_name}} – saw your post about {{recentPostTopic}}.\n\nHow much of your DevOps team\'s time is going to cost optimization vs. building?',
      cta: 'Curious—is this a bottleneck?',
    },
    creativeIdeas: [
      { feature: 'Resource right-sizing', action: 'Auto-scale instances', target: 'dev/staging environments', benefit: 'cuts non-prod spend 60% with zero manual work' },
      { feature: 'Spot instance automation', action: 'Migrate batch jobs', target: 'data pipelines', benefit: 'saves 70% on compute for fault-tolerant workloads' },
      { feature: 'Cost anomaly detection', action: 'Alert on spend spikes', target: 'all environments', benefit: 'catches runaway costs before they hit the bill' },
    ],
    qaScore: { total: 84, situationRecognition: 21, valueClarity: 21, personalizationQuality: 18, ctaEffort: 12, length: 8, subjectLine: 4 },
    status: 'pending',
    generatedAt: daysAgo(3),
  },
  {
    id: 'idea-10',
    clientId: 'client-4',
    industry: 'Technology',
    segment: 'CFOs',
    title: 'CFO-Friendly ROI',
    angle: 'Speak the language of finance. Present cloud optimization as a guaranteed ROI investment.',
    campaignType: 'whole_offer',
    icpDescription: 'CFOs at tech companies with $1M+ annual cloud spend seeking cost controls.',
    valueProposition: {
      business: 'Guaranteed 3x ROI on cloud optimization within 90 days',
      personal: 'Show the board you\'re driving operational efficiency',
    },
    variables: {
      core: { firstName: '{{first_name}}', companyName: '{{company_name}}' },
      caseStudy: { company: 'DataDriven Inc', result: '$1.2M saved', metric: 'annual cloud spend', timeframe: 'first year' },
    },
    email1: {
      subject: 'Cloud ROI',
      body: '{{first_name}} – CFOs at companies your size typically find $200-500k in cloud waste.\n\nDataDriven Inc saved $1.2M in their first year.\n\nWe guarantee 3x ROI or you don\'t pay.\n\nWorth a conversation?',
      cta: 'Worth a conversation?',
    },
    qaScore: { total: 81, situationRecognition: 20, valueClarity: 22, personalizationQuality: 16, ctaEffort: 12, length: 7, subjectLine: 4 },
    status: 'editing',
    generatedAt: daysAgo(3),
  },
];

// ============ CAMPAIGNS ============
export const mockCampaigns: Campaign[] = [
  // TechFlow campaigns
  { id: 'campaign-1', clientId: 'client-1', ideaId: 'idea-1', name: 'Remote Team Pain Points', industry: 'SaaS', segment: 'Series A Startups', angle: 'Address the communication gaps that plague distributed teams.', status: 'active', leadsTotal: 1250, leadsContacted: 890, leadsCapacity: 3000, repliesCount: 67, createdAt: daysAgo(32) },
  { id: 'campaign-2', clientId: 'client-1', ideaId: 'idea-2', name: 'Productivity Benchmark', industry: 'SaaS', segment: 'Series B Startups', angle: 'Share data on how top-performing remote teams operate.', status: 'active', leadsTotal: 800, leadsContacted: 320, leadsCapacity: 3000, repliesCount: 28, createdAt: daysAgo(28) },
  // GrowthMetrics campaigns
  { id: 'campaign-3', clientId: 'client-2', ideaId: 'idea-5', name: 'ABM Success Stories', industry: 'Marketing Agency', segment: 'B2B Tech', angle: 'Lead with case studies of similar companies achieving 3x pipeline growth.', status: 'active', leadsTotal: 650, leadsContacted: 480, leadsCapacity: 3000, repliesCount: 42, createdAt: daysAgo(22) },
  // CloudScale campaigns
  { id: 'campaign-4', clientId: 'client-4', ideaId: 'idea-8', name: 'Cloud Cost Shock', industry: 'Technology', segment: 'High Cloud Spend', angle: 'Lead with the surprising statistic that most companies overspend on cloud.', status: 'draft', leadsTotal: 200, leadsContacted: 0, leadsCapacity: 3000, repliesCount: 0, createdAt: daysAgo(8) },
];

// ============ LEADS ============
// Generate mock leads for campaigns
const FIRST_NAMES = ['James', 'Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'William', 'Sophia', 'Benjamin', 'Isabella', 'Lucas', 'Mia', 'Henry', 'Charlotte', 'Alexander', 'Amelia', 'Daniel', 'Harper', 'Michael', 'Evelyn'];
const LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin'];
const COMPANIES = ['Acme Corp', 'TechVentures', 'StartupCo', 'Innovation Labs', 'Digital Dynamics', 'FutureTech', 'CloudNine', 'DataDriven', 'AgileWorks', 'ScaleUp Inc', 'GrowthHQ', 'ProductForce', 'EngineeringPros', 'SalesForward', 'MarketMasters'];
const TITLES = ['CEO', 'CTO', 'VP Engineering', 'VP Sales', 'Head of Growth', 'Director of Marketing', 'Engineering Manager', 'Product Manager', 'Head of Operations', 'COO', 'Founder', 'Co-Founder'];

function generateLeads(campaignId: string, count: number, contactedRatio: number): Lead[] {
  const leads: Lead[] = [];

  for (let i = 0; i < count; i++) {
    const firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
    const lastName = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
    const company = COMPANIES[Math.floor(Math.random() * COMPANIES.length)];

    let status: Lead['status'] = 'queued';
    let contactedAt: Date | undefined;

    if (i < count * contactedRatio) {
      const rand = Math.random();
      if (rand > 0.92) {
        status = 'bounced';
      } else if (rand > 0.85) {
        status = 'replied';
      } else {
        status = 'contacted';
      }
      contactedAt = daysAgo(Math.floor(Math.random() * 20));
    }

    leads.push({
      id: `lead-${campaignId}-${i}`,
      campaignId,
      email: `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${company.toLowerCase().replace(/\s/g, '')}.com`,
      firstName,
      lastName,
      company,
      title: TITLES[Math.floor(Math.random() * TITLES.length)],
      status,
      contactedAt,
    });
  }

  return leads;
}

export const mockLeads: Lead[] = [
  ...generateLeads('campaign-1', 50, 0.7), // 50 leads, 70% contacted
  ...generateLeads('campaign-2', 40, 0.4), // 40 leads, 40% contacted
  ...generateLeads('campaign-3', 35, 0.75), // 35 leads, 75% contacted
  ...generateLeads('campaign-4', 20, 0), // 20 leads, none contacted (draft)
];
