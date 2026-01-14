import { create } from 'zustand';
import type { Domain, Inbox, DomainStatus, InboxStatus, OnboardingData } from '@/lib/types';
import { api } from '@/lib/api';

interface InfrastructureStore {
  domains: Domain[];
  inboxes: Inbox[];
  isLoading: boolean;
  error: string | null;

  // Domain actions
  setDomains: (domains: Domain[]) => void;
  updateDomainLocal: (id: string, data: Partial<Domain>) => void;
  getDomainsByClient: (clientId: string) => Domain[];
  getApprovedDomainsByClient: (clientId: string) => Domain[];

  // Inbox actions
  setInboxes: (inboxes: Inbox[]) => void;
  updateInboxLocal: (id: string, data: Partial<Inbox>) => void;
  getInboxesByClient: (clientId: string) => Inbox[];
  getInboxesByDomain: (domainId: string) => Inbox[];

  // Async API actions - Domains
  fetchDomainsByClient: (clientId: string) => Promise<void>;
  addDomain: (data: { clientId: string; domain: string }) => Promise<Domain>;
  updateDomain: (id: string, data: Partial<Domain>) => Promise<void>;
  approveDomain: (id: string) => Promise<void>;
  rejectDomain: (id: string) => Promise<void>;
  resetDomainStatus: (id: string) => Promise<void>;
  generateDomainsFromOnboarding: (clientId: string, onboarding: OnboardingData) => Promise<Domain[]>;

  // Async API actions - Inboxes
  fetchInboxesByClient: (clientId: string) => Promise<void>;
  fetchInboxesByDomain: (domainId: string) => Promise<void>;
  addInbox: (data: {
    clientId: string;
    domainId: string;
    firstName: string;
    lastName: string;
    email: string;
  }) => Promise<Inbox>;
  updateInbox: (id: string, data: Partial<Inbox>) => Promise<void>;
  approveInbox: (id: string) => Promise<void>;
  rejectInbox: (id: string) => Promise<void>;
  resetInboxStatus: (id: string) => Promise<void>;
  generateInboxesFromOnboarding: (clientId: string, domainId: string, domain: string, onboarding: OnboardingData) => Promise<Inbox[]>;
}

export const useInfrastructureStore = create<InfrastructureStore>((set, get) => ({
  domains: [],
  inboxes: [],
  isLoading: false,
  error: null,

  // Local state setters
  setDomains: (domains) => set({ domains }),
  setInboxes: (inboxes) => set({ inboxes }),

  updateDomainLocal: (id, data) => {
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, ...data } : domain
      ),
    }));
  },

  updateInboxLocal: (id, data) => {
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, ...data } : inbox
      ),
    }));
  },

  // Local getters
  getDomainsByClient: (clientId) => {
    return get().domains.filter((d) => d.clientId === clientId);
  },

  getApprovedDomainsByClient: (clientId) => {
    return get().domains.filter(
      (d) => d.clientId === clientId && (d.status === 'approved' || d.status === 'active' || d.status === 'warming')
    );
  },

  getInboxesByClient: (clientId) => {
    return get().inboxes.filter((i) => i.clientId === clientId);
  },

  getInboxesByDomain: (domainId) => {
    return get().inboxes.filter((i) => i.domainId === domainId);
  },

  // Async API actions - Domains
  fetchDomainsByClient: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.domains.list({ clientId });
      // Merge with existing domains (update if exists, add if not)
      set((state) => {
        const otherDomains = state.domains.filter((d) => d.clientId !== clientId);
        return { domains: [...otherDomains, ...data.items], isLoading: false };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  addDomain: async (data) => {
    set({ isLoading: true, error: null });
    try {
      // api.domains.create does not exist - use generate with count=1
      const result = await api.domains.generate(data.clientId, data.domain, 1);
      const newDomain = result.domain as unknown as Domain;
      set((state) => ({
        domains: newDomain ? [...state.domains, newDomain] : state.domains,
        isLoading: false,
      }));
      return newDomain;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateDomain: async (id, data) => {
    // Local-only update - api.domains.update does not exist
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, ...data } : domain
      ),
    }));
  },

  approveDomain: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.domains.approve(id);
      set((state) => ({
        domains: state.domains.map((domain) =>
          domain.id === id ? updated : domain
        ),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  rejectDomain: async (id) => {
    // Local-only update - api.domains.update does not exist
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, status: 'rejected' as DomainStatus } : domain
      ),
    }));
  },

  resetDomainStatus: async (id) => {
    // Local-only update - api.domains.update does not exist
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, status: 'pending_approval' as DomainStatus } : domain
      ),
    }));
  },

  generateDomainsFromOnboarding: async (clientId, onboarding) => {
    set({ isLoading: true, error: null });
    try {
      const primaryDomain = onboarding.primaryDomain || '';
      const result = await api.domains.generate(clientId, primaryDomain, 5);
      // generate returns { message, domain? } - domain is a single optional domain
      const newDomain = result.domain as unknown as Domain | undefined;
      const newDomains = newDomain ? [newDomain] : [];
      set((state) => ({
        domains: [...state.domains, ...newDomains],
        isLoading: false,
      }));
      return newDomains;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  // Async API actions - Inboxes
  fetchInboxesByClient: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.inboxes.list({ clientId });
      set((state) => {
        const otherInboxes = state.inboxes.filter((i) => i.clientId !== clientId);
        return { inboxes: [...otherInboxes, ...data.items], isLoading: false };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  fetchInboxesByDomain: async (domainId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.inboxes.list({ domainId });
      set((state) => {
        const otherInboxes = state.inboxes.filter((i) => i.domainId !== domainId);
        return { inboxes: [...otherInboxes, ...data.items], isLoading: false };
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  addInbox: async (data) => {
    set({ isLoading: true, error: null });
    try {
      // api.inboxes.create does not exist - use generate with single name
      const result = await api.inboxes.generate(data.clientId, data.domainId, [data.firstName], 1);
      const newInbox = result.inboxes?.[0] as unknown as Inbox;
      set((state) => ({
        inboxes: newInbox ? [...state.inboxes, newInbox] : state.inboxes,
        isLoading: false,
      }));
      return newInbox;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateInbox: async (id, data) => {
    // Local-only update - api.inboxes.update does not exist
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, ...data } : inbox
      ),
    }));
  },

  approveInbox: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.inboxes.approve(id);
      set((state) => ({
        inboxes: state.inboxes.map((inbox) =>
          inbox.id === id ? updated : inbox
        ),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  rejectInbox: async (id) => {
    // Local-only update - api.inboxes.update does not exist
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, status: 'rejected' as InboxStatus } : inbox
      ),
    }));
  },

  resetInboxStatus: async (id) => {
    // Local-only update - api.inboxes.update does not exist
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, status: 'pending_approval' as InboxStatus } : inbox
      ),
    }));
  },

  generateInboxesFromOnboarding: async (clientId, domainId, _domain, onboarding) => {
    set({ isLoading: true, error: null });
    try {
      // Extract first names from onboarding data
      const firstNames = onboarding.contactFirstNames?.length > 0 ? onboarding.contactFirstNames : ['Sales', 'Support'];
      const result = await api.inboxes.generate(clientId, domainId, firstNames, firstNames.length);
      // generate returns { message, inboxes: Record<string, unknown>[] }
      const newInboxes = (result.inboxes || []) as unknown as Inbox[];
      set((state) => ({
        inboxes: [...state.inboxes, ...newInboxes],
        isLoading: false,
      }));
      return newInboxes;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },
}));
