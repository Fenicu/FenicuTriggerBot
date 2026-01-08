import { create } from 'zustand';

interface Stats {
  totalUsers: number;
  totalChats: number;
  activeChats: number;
}

interface AppState {
  stats: Stats | null;
  setStats: (stats: Stats) => void;
}

export const useAppStore = create<AppState>((set) => ({
  stats: null,
  setStats: (stats) => set({ stats }),
}));
