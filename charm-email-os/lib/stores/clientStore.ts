import { create } from 'zustand';
import type { Client, OnboardingData, Workspace } from '@/lib/types';
import { api } from '@/lib/api';

interface ClientStore {
  clients: Client[];
  workspaces: Workspace[];
  selectedClientId: string | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  setClients: (clients: Client[]) => void;
  setWorkspaces: (workspaces: Workspace[]) => void;
  selectClient: (id: string | null) => void;
  getClient: (id: string) => Client | undefined;
  getSelectedClient: () => Client | undefined;

  // Async API actions
  fetchClients: () => Promise<void>;
  fetchWorkspaces: () => Promise<void>;
  addClient: (data: { name: string; domain: string }) => Promise<Client>;
  updateClient: (id: string, data: Partial<Client>) => Promise<void>;
  completeOnboarding: (id: string, data: OnboardingData) => Promise<void>;
  linkWorkspace: (clientId: string, workspaceId: string) => Promise<void>;
}

export const useClientStore = create<ClientStore>((set, get) => ({
  clients: [],
  workspaces: [],
  selectedClientId: null,
  isLoading: false,
  error: null,

  setClients: (clients) => set({ clients }),
  setWorkspaces: (workspaces) => set({ workspaces }),

  selectClient: (id) => set({ selectedClientId: id }),

  getClient: (id) => get().clients.find((c) => c.id === id),

  getSelectedClient: () => {
    const { clients, selectedClientId } = get();
    return clients.find((c) => c.id === selectedClientId);
  },

  // Fetch all clients from API
  fetchClients: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.clients.list();
      set({ clients: data.items, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  // Fetch all workspaces from API
  fetchWorkspaces: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await api.workspaces.list();
      set({ workspaces: data.items, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  // Create a new client via API
  addClient: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const newClient = await api.clients.create({
        name: data.name,
        onboardingData: data.domain ? { primaryDomain: data.domain } : undefined,
      });
      set((state) => ({
        clients: [...state.clients, newClient],
        isLoading: false,
      }));
      return newClient;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  // Update client via API
  updateClient: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.clients.update(id, data);
      set((state) => ({
        clients: state.clients.map((client) =>
          client.id === id ? updated : client
        ),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  // Complete onboarding via API
  completeOnboarding: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.clients.completeOnboarding(id, data);
      set((state) => ({
        clients: state.clients.map((client) =>
          client.id === id ? updated : client
        ),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  // Link client to workspace via API
  linkWorkspace: async (clientId, workspaceId) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.clients.linkWorkspace(clientId, workspaceId);
      set((state) => ({
        clients: state.clients.map((client) =>
          client.id === clientId ? updated : client
        ),
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },
}));
