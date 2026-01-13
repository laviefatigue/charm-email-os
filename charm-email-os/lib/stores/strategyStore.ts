import { create } from 'zustand';
import { nanoid } from 'nanoid';
import type { CampaignIdea, CampaignIdeaStatus } from '@/lib/types';

// Sample campaign angles for generation
const SAMPLE_ANGLES = [
  {
    title: 'Pain Point Pivot',
    angle: 'Address the #1 frustration your prospects face daily. Lead with empathy, then position your solution as the obvious fix.',
  },
  {
    title: 'Industry Benchmark',
    angle: 'Share surprising statistics about their industry performance. Create urgency by highlighting the gap between average and top performers.',
  },
  {
    title: 'Case Study Teaser',
    angle: 'Reference a similar company\'s success story without revealing all details. Build curiosity that leads to a conversation.',
  },
  {
    title: 'Time-Sensitive Opportunity',
    angle: 'Highlight a market shift or upcoming change that makes now the perfect time to act.',
  },
  {
    title: 'Mutual Connection',
    angle: 'Leverage shared connections, events, or communities to establish immediate credibility and relevance.',
  },
  {
    title: 'Contrarian Take',
    angle: 'Challenge conventional wisdom in their industry. Stand out by offering a fresh perspective that makes them think.',
  },
  {
    title: 'Quick Win Offer',
    angle: 'Promise a specific, achievable result within a short timeframe. Lower the barrier to engagement with immediate value.',
  },
  {
    title: 'Competitor Gap',
    angle: 'Subtly highlight what competitors are missing. Position yourself as the comprehensive solution.',
  },
];

interface StrategyStore {
  ideas: CampaignIdea[];

  // Actions
  setIdeas: (ideas: CampaignIdea[]) => void;
  generateIdeas: (clientId: string, industry: string, segment: string) => CampaignIdea[];
  approveIdea: (id: string) => void;
  rejectIdea: (id: string) => void;
  updateIdea: (id: string, data: Partial<CampaignIdea>) => void;
  resetIdeaStatus: (id: string) => void;
  getIdeasByClient: (clientId: string) => CampaignIdea[];
  getPendingIdeas: (clientId: string) => CampaignIdea[];
  getApprovedIdeas: (clientId: string) => CampaignIdea[];
}

export const useStrategyStore = create<StrategyStore>((set, get) => ({
  ideas: [],

  setIdeas: (ideas) => set({ ideas }),

  generateIdeas: (clientId, industry, segment) => {
    // Generate 3-4 random ideas
    const count = Math.floor(Math.random() * 2) + 3; // 3-4 ideas
    const shuffled = [...SAMPLE_ANGLES].sort(() => Math.random() - 0.5);
    const selected = shuffled.slice(0, count);

    const newIdeas: CampaignIdea[] = selected.map((sample) => ({
      id: nanoid(),
      clientId,
      industry,
      segment,
      title: sample.title,
      angle: sample.angle,
      status: 'pending' as CampaignIdeaStatus,
      generatedAt: new Date(),
    }));

    set((state) => ({ ideas: [...state.ideas, ...newIdeas] }));
    return newIdeas;
  },

  approveIdea: (id) => {
    set((state) => ({
      ideas: state.ideas.map((idea) =>
        idea.id === id ? { ...idea, status: 'approved' as CampaignIdeaStatus } : idea
      ),
    }));
  },

  rejectIdea: (id) => {
    set((state) => ({
      ideas: state.ideas.map((idea) =>
        idea.id === id ? { ...idea, status: 'editing' as CampaignIdeaStatus } : idea
      ),
    }));
  },

  updateIdea: (id, data) => {
    set((state) => ({
      ideas: state.ideas.map((idea) =>
        idea.id === id ? { ...idea, ...data } : idea
      ),
    }));
  },

  resetIdeaStatus: (id) => {
    set((state) => ({
      ideas: state.ideas.map((idea) =>
        idea.id === id ? { ...idea, status: 'pending' as CampaignIdeaStatus } : idea
      ),
    }));
  },

  getIdeasByClient: (clientId) => {
    return get().ideas.filter((i) => i.clientId === clientId);
  },

  getPendingIdeas: (clientId) => {
    return get().ideas.filter(
      (i) => i.clientId === clientId && (i.status === 'pending' || i.status === 'editing')
    );
  },

  getApprovedIdeas: (clientId) => {
    return get().ideas.filter((i) => i.clientId === clientId && i.status === 'approved');
  },
}));
