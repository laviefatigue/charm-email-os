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
      const data = await api.domains.listByClient(clientId);
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
      const newDomain = await api.domains.create(data);
      set((state) => ({
        domains: [...state.domains, newDomain],
        isLoading: false,
      }));
      return newDomain;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateDomain: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.domains.update(id, data);
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
    // Optimistic update
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, status: 'rejected' as DomainStatus } : domain
      ),
    }));
    try {
      await api.domains.update(id, { status: 'rejected' });
    } catch (error) {
      // Rollback on error
      set((state) => ({
        domains: state.domains.map((domain) =>
          domain.id === id ? { ...domain, status: 'pending_approval' as DomainStatus } : domain
        ),
        error: (error as Error).message,
      }));
    }
  },

  resetDomainStatus: async (id) => {
    set((state) => ({
      domains: state.domains.map((domain) =>
        domain.id === id ? { ...domain, status: 'pending_approval' as DomainStatus } : domain
      ),
    }));
    try {
      await api.domains.update(id, { status: 'pending_approval' });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  generateDomainsFromOnboarding: async (clientId, onboarding) => {
    set({ isLoading: true, error: null });
    try {
      const newDomains = await api.domains.generate(clientId, onboarding);
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
      const data = await api.inboxes.listByClient(clientId);
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
      const data = await api.inboxes.listByDomain(domainId);
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
      const newInbox = await api.inboxes.create(data);
      set((state) => ({
        inboxes: [...state.inboxes, newInbox],
        isLoading: false,
      }));
      return newInbox;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  updateInbox: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.inboxes.update(id, data);
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
    // Optimistic update
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, status: 'rejected' as InboxStatus } : inbox
      ),
    }));
    try {
      await api.inboxes.update(id, { status: 'rejected' });
    } catch (error) {
      set((state) => ({
        inboxes: state.inboxes.map((inbox) =>
          inbox.id === id ? { ...inbox, status: 'pending_approval' as InboxStatus } : inbox
        ),
        error: (error as Error).message,
      }));
    }
  },

  resetInboxStatus: async (id) => {
    set((state) => ({
      inboxes: state.inboxes.map((inbox) =>
        inbox.id === id ? { ...inbox, status: 'pending_approval' as InboxStatus } : inbox
      ),
    }));
    try {
      await api.inboxes.update(id, { status: 'pending_approval' });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  generateInboxesFromOnboarding: async (clientId, domainId, domain, onboarding) => {
    set({ isLoading: true, error: null });
    try {
      const newInboxes = await api.inboxes.generate(clientId, domainId, domain, onboarding);
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
