import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ============ Types ============

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

export interface ConfirmModal {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'default';
  onConfirm: () => void;
  onCancel: () => void;
}

export interface AuthState {
  isAuthenticated: boolean;
  authType: 'webapp' | 'widget' | null;
  userId: number | null;
  username: string | null;
}

export interface Stats {
  totalUsers: number;
  totalChats: number;
  activeChats: number;
  totalTriggers: number;
}

// ============ Store Interface ============

interface AppState {
  // Auth
  auth: AuthState;
  setAuth: (auth: Partial<AuthState>) => void;
  logout: () => void;

  // Stats
  stats: Stats | null;
  setStats: (stats: Stats) => void;

  // Toasts
  toasts: Toast[];
  addToast: (message: string, type?: ToastType, duration?: number) => void;
  removeToast: (id: string) => void;

  // Confirm Modal
  confirmModal: ConfirmModal;
  showConfirm: (options: {
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    variant?: 'danger' | 'warning' | 'default';
    onConfirm: () => void;
    onCancel?: () => void;
  }) => void;
  hideConfirm: () => void;

  // Loading states
  globalLoading: boolean;
  setGlobalLoading: (loading: boolean) => void;
}

// ============ Initial States ============

const initialAuthState: AuthState = {
  isAuthenticated: false,
  authType: null,
  userId: null,
  username: null,
};

const initialConfirmModal: ConfirmModal = {
  isOpen: false,
  title: '',
  message: '',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  variant: 'default',
  onConfirm: () => {},
  onCancel: () => {},
};

// ============ Store ============

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Auth
      auth: initialAuthState,
      setAuth: (auth) =>
        set((state) => ({
          auth: { ...state.auth, ...auth },
        })),
      logout: () => {
        localStorage.removeItem('auth_data');
        set({ auth: initialAuthState });
      },

      // Stats
      stats: null,
      setStats: (stats) => set({ stats }),

      // Toasts
      toasts: [],
      addToast: (message, type = 'info', duration = 3000) => {
        const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        set((state) => ({
          toasts: [...state.toasts, { id, message, type, duration }],
        }));

        // Auto-remove after duration
        if (duration > 0) {
          setTimeout(() => {
            get().removeToast(id);
          }, duration);
        }
      },
      removeToast: (id) =>
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        })),

      // Confirm Modal
      confirmModal: initialConfirmModal,
      showConfirm: ({ title, message, confirmText, cancelText, variant, onConfirm, onCancel }) =>
        set({
          confirmModal: {
            isOpen: true,
            title,
            message,
            confirmText: confirmText || 'Confirm',
            cancelText: cancelText || 'Cancel',
            variant: variant || 'default',
            onConfirm,
            onCancel: onCancel || (() => get().hideConfirm()),
          },
        }),
      hideConfirm: () =>
        set({
          confirmModal: initialConfirmModal,
        }),

      // Loading
      globalLoading: false,
      setGlobalLoading: (loading) => set({ globalLoading: loading }),
    }),
    {
      name: 'trigger-app-storage',
      partialize: (state) => ({
        // Only persist auth state
        auth: state.auth,
      }),
    }
  )
);

// ============ Selectors (for better performance) ============

export const useAuth = () => useAppStore((state) => state.auth);
export const useToasts = () => useAppStore((state) => state.toasts);
export const useConfirmModal = () => useAppStore((state) => state.confirmModal);
export const useStats = () => useAppStore((state) => state.stats);

// ============ Actions (for cleaner imports) ============

export const { addToast, removeToast, showConfirm, hideConfirm, setAuth, logout, setStats, setGlobalLoading } =
  useAppStore.getState();

// Helper functions for common toast types
export const toast = {
  success: (message: string, duration?: number) => useAppStore.getState().addToast(message, 'success', duration),
  error: (message: string, duration?: number) => useAppStore.getState().addToast(message, 'error', duration ?? 5000),
  warning: (message: string, duration?: number) => useAppStore.getState().addToast(message, 'warning', duration),
  info: (message: string, duration?: number) => useAppStore.getState().addToast(message, 'info', duration),
};

// Helper function for confirm dialog (returns Promise)
export const confirm = (options: {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'default';
}): Promise<boolean> => {
  return new Promise((resolve) => {
    useAppStore.getState().showConfirm({
      ...options,
      onConfirm: () => {
        useAppStore.getState().hideConfirm();
        resolve(true);
      },
      onCancel: () => {
        useAppStore.getState().hideConfirm();
        resolve(false);
      },
    });
  });
};
