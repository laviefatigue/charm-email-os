import { create } from 'zustand';
import { nanoid } from 'nanoid';
import type { Campaign, Lead, OwnRBLCampaignStatus, LeadStatus, CampaignIdea } from '@/lib/types';
import { api } from '@/lib/api';

interface CampaignStore {
  campaigns: Campaign[];
  leads: Lead[];
  isLoading: boolean;
  error: string | null;

  // Campaign actions
  setCampaigns: (campaigns: Campaign[]) => void;
  updateCampaignLocal: (id: string, data: Partial<Campaign>) => void;
  getCampaignsByClient: (clientId: string) => Campaign[];
  getCampaign: (id: string) => Campaign | undefined;

  // Lead actions
  setLeads: (leads: Lead[]) => void;
  updateLeadLocal: (id: string, data: Partial<Lead>) => void;
  getLeadsByCampaign: (campaignId: string) => Lead[];

  // Async API actions - Campaigns
  fetchCampaignsByClient: (clientId: string) => Promise<void>;
  createCampaignFromIdea: (idea: CampaignIdea) => Promise<Campaign>;
  updateCampaign: (id: string, data: Partial<Campaign>) => Promise<void>;
  runCampaign: (id: string) => Promise<void>;
  pauseCampaign: (id: string) => Promise<void>;

  // Async API actions - Leads
  fetchLeadsByCampaign: (campaignId: string) => Promise<void>;
  uploadLeads: (campaignId: string, leads: Omit<Lead, 'id' | 'campaignId' | 'status'>[]) => Promise<void>;
  updateLeadStatus: (id: string, status: LeadStatus) => Promise<void>;

  // Local simulation (for demo/development)
  simulateUploadLeads: (campaignId: string, count: number) => void;
  simulateCampaignProgress: (campaignId: string) => void;
}

export const useCampaignStore = create<CampaignStore>((set, get) => ({
  campaigns: [],
  leads: [],
  isLoading: false,
  error: null,

  // Local setters
  setCampaigns: (campaigns) => set({ campaigns }),
  setLeads: (leads) => set({ leads }),

  updateCampaignLocal: (id, data) => {
    set((state) => ({
      campaigns: state.campaigns.map((campaign) =>
        campaign.id === id ? { ...campaign, ...data } : campaign
      ),
    }));
  },

  updateLeadLocal: (id, data) => {
    set((state) => ({
      leads: state.leads.map((lead) =>
        lead.id === id ? { ...lead, ...data } : lead
      ),
    }));
  },

  // Local getters
  getCampaignsByClient: (clientId) => {
    return get().campaigns.filter((c) => c.clientId === clientId);
  },

  getCampaign: (id) => {
    return get().campaigns.find((c) => c.id === id);
  },

  getLeadsByCampaign: (campaignId) => {
    return get().leads.filter((l) => l.campaignId === campaignId);
  },

  // Async API actions - Campaigns
  fetchCampaignsByClient: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.campaigns.list({ clientId });
      set((state) => {
        const otherCampaigns = state.campaigns.filter((c) => c.clientId !== clientId);
        return { campaigns: [...otherCampaigns, ...data.items], isLoading: false };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  createCampaignFromIdea: async (idea) => {
    set({ isLoading: true, error: null });
    try {
      const newCampaign = await api.campaigns.create({
        workspaceId: `ws-${idea.clientId}`,  // TODO: get actual workspaceId from client
        ideaId: idea.id,
        campaignName: idea.title,
        industry: idea.industry,
        segment: idea.segment,
        angle: idea.angle,
      });
      set((state) => ({
        campaigns: [...state.campaigns, newCampaign],
        isLoading: false,
      }));
      return newCampaign;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateCampaign: async (id, data) => {
    // Local-only update - api.campaigns.update does not exist
    set((state) => ({
      campaigns: state.campaigns.map((campaign) =>
        campaign.id === id ? { ...campaign, ...data } : campaign
      ),
    }));
  },

  runCampaign: async (id) => {
    // Optimistic update
    set((state) => ({
      campaigns: state.campaigns.map((campaign) =>
        campaign.id === id ? { ...campaign, status: 'active' as OwnRBLCampaignStatus } : campaign
      ),
    }));
    try {
      await api.campaigns.run(id);
    } catch (error) {
      // Rollback
      set((state) => ({
        campaigns: state.campaigns.map((campaign) =>
          campaign.id === id ? { ...campaign, status: 'draft' as OwnRBLCampaignStatus } : campaign
        ),
        error: (error as Error).message,
      }));
    }
  },

  pauseCampaign: async (id) => {
    // Optimistic update
    const campaign = get().campaigns.find((c) => c.id === id);
    const previousStatus = campaign?.status;

    set((state) => ({
      campaigns: state.campaigns.map((c) =>
        c.id === id ? { ...c, status: 'paused' as OwnRBLCampaignStatus } : c
      ),
    }));
    try {
      await api.campaigns.pause(id);
    } catch (error) {
      // Rollback
      set((state) => ({
        campaigns: state.campaigns.map((c) =>
          c.id === id ? { ...c, status: previousStatus || 'active' } : c
        ),
        error: (error as Error).message,
      }));
    }
  },

  // Async API actions - Leads
  fetchLeadsByCampaign: async (campaignId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.leads.getByCampaign(campaignId);
      set((state) => {
        const otherLeads = state.leads.filter((l) => l.campaignId !== campaignId);
        return { leads: [...otherLeads, ...data.items], isLoading: false };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  uploadLeads: async (campaignId, newLeads) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.leads.bulkCreate(campaignId, newLeads);
      // bulkCreate returns { total_uploaded, successful, failed, duplicates_skipped }
      // Re-fetch leads to get actual lead objects
      const data = await api.leads.getByCampaign(campaignId);
      set((state) => {
        const otherLeads = state.leads.filter((l) => l.campaignId !== campaignId);
        const updatedLeads = [...otherLeads, ...data.items];
        const totalForCampaign = data.items.length;

        return {
          leads: updatedLeads,
          campaigns: state.campaigns.map((c) =>
            c.id === campaignId ? { ...c, leadsTotal: totalForCampaign } : c
          ),
          isLoading: false,
        };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateLeadStatus: async (id, status) => {
    // Optimistic update
    set((state) => ({
      leads: state.leads.map((lead) =>
        lead.id === id
          ? {
              ...lead,
              status,
              contactedAt: status === 'contacted' ? new Date() : lead.contactedAt,
            }
          : lead
      ),
    }));
    try {
      await api.leads.updateStatus(id, status);
    } catch (error) {
      // Rollback
      set((state) => ({
        leads: state.leads.map((lead) =>
          lead.id === id ? { ...lead, status: 'queued' as LeadStatus } : lead
        ),
        error: (error as Error).message,
      }));
    }
  },

  // Local simulation for demo/development
  simulateUploadLeads: (campaignId, count) => {
    const firstNames = ['James', 'Emma', 'Oliver', 'Sophia', 'William', 'Ava', 'Benjamin', 'Isabella', 'Lucas', 'Mia'];
    const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Wilson', 'Moore'];
    const companies = ['TechVentures', 'DataFlow', 'CloudSync', 'InnovateLabs', 'NexGen', 'ByteCraft', 'Quantum', 'Elevate'];
    const titles = ['CEO', 'CTO', 'VP Sales', 'Head of Marketing', 'Director of Operations', 'Founder', 'COO', 'CMO'];

    const mockLeads: Lead[] = Array.from({ length: count }, () => {
      const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
      const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];
      const company = companies[Math.floor(Math.random() * companies.length)];

      return {
        id: nanoid(),
        campaignId,
        firstName,
        lastName,
        email: `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${company.toLowerCase()}.com`,
        company,
        title: titles[Math.floor(Math.random() * titles.length)],
        status: 'queued' as LeadStatus,
      };
    });

    set((state) => {
      const updatedLeads = [...state.leads, ...mockLeads];
      const totalForCampaign = updatedLeads.filter((l) => l.campaignId === campaignId).length;

      return {
        leads: updatedLeads,
        campaigns: state.campaigns.map((c) =>
          c.id === campaignId ? { ...c, leadsTotal: totalForCampaign } : c
        ),
      };
    });
  },

  simulateCampaignProgress: (campaignId) => {
    const { leads } = get();
    const campaignLeads = leads.filter((l) => l.campaignId === campaignId);
    const queuedLeads = campaignLeads.filter((l) => l.status === 'queued');

    if (queuedLeads.length === 0) return;

    const toContact = queuedLeads.slice(0, Math.min(Math.floor(Math.random() * 6) + 5, queuedLeads.length));

    set((state) => {
      const updatedLeads = state.leads.map((lead) => {
        if (toContact.find((l) => l.id === lead.id)) {
          const rand = Math.random();
          let newStatus: LeadStatus = 'contacted';
          if (rand > 0.9) newStatus = 'bounced';
          else if (rand > 0.7) newStatus = 'replied';

          return {
            ...lead,
            status: newStatus,
            contactedAt: new Date(),
          };
        }
        return lead;
      });

      const updatedCampaignLeads = updatedLeads.filter((l) => l.campaignId === campaignId);
      const contacted = updatedCampaignLeads.filter((l) => l.status !== 'queued').length;
      const replies = updatedCampaignLeads.filter((l) => l.status === 'replied').length;

      return {
        leads: updatedLeads,
        campaigns: state.campaigns.map((c) =>
          c.id === campaignId
            ? { ...c, leadsContacted: contacted, repliesCount: replies }
            : c
        ),
      };
    });
  },
}));
