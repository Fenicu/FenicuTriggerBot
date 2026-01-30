import axios, { type InternalAxiosRequestConfig, type AxiosError } from 'axios';
import { retrieveLaunchParams } from '@telegram-apps/sdk-react';
import { toast } from '../store/store';
import type {
  CaptchaResponse,
  Trigger,
  TriggerListResponse,
  TriggerQueueStatus,
  ModerationHistoryItem,
  ModerationHistoryResponse,
  User,
  Chat,
  ChatUser,
  PaginatedResponse,
  StatsResponse,
  UpdateUserRoleRequest,
  BanChatRequest,
} from '../types';

// ============ Axios Instance ============

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
});

// ============ Request Interceptor ============

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  let initData = '';

  // Try to get initData from Telegram SDK
  try {
    const { initDataRaw } = retrieveLaunchParams();
    if (initDataRaw && typeof initDataRaw === 'string') {
      initData = initDataRaw;
    }
  } catch {
    // SDK not available, try window.Telegram
  }

  // Fallback to window.Telegram.WebApp
  if (!initData && window.Telegram?.WebApp?.initData) {
    initData = window.Telegram.WebApp.initData;
  }

  // Set authorization header
  if (initData) {
    config.headers.set('Authorization', `twa-init-data ${initData}`);
  } else {
    const storedAuth = localStorage.getItem('auth_data');
    if (storedAuth) {
      config.headers.set('Authorization', `login-widget-data ${storedAuth}`);
    }
  }

  // Debug logging only in development
  if (import.meta.env.DEV) {
    console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
  }

  return config;
});

// ============ Response Interceptor ============

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    // Handle 401 - redirect to login
    if (error.response?.status === 401) {
      if (!window.location.hash.includes('#/login') && !window.location.hash.includes('#/captcha')) {
        window.location.hash = '#/login';
      }
    }

    // Extract error message
    const message = error.response?.data?.detail || error.message || 'An error occurred';

    // Don't show toast for:
    // - 401 (handled by redirect)
    // - 404 on photo endpoints (expected when no avatar)
    const isPhotoRequest = error.config?.url?.endsWith('/photo');
    const shouldShowToast = error.response?.status !== 401 &&
      !(error.response?.status === 404 && isPhotoRequest);

    if (shouldShowToast) {
      toast.error(message);
    }

    return Promise.reject(error);
  }
);

// ============ Captcha API ============

export const captchaApi = {
  check: async (initData?: string) => {
    const config = initData ? { headers: { Authorization: `twa-init-data ${initData}` } } : {};
    const response = await apiClient.get<CaptchaResponse>('/captcha/check', config);
    return response.data;
  },

  solve: async (initData?: string) => {
    const config = initData ? { headers: { Authorization: `twa-init-data ${initData}` } } : {};
    const response = await apiClient.post<{ ok: boolean }>('/captcha/solve', {}, config);
    return response.data;
  },
};

// ============ Triggers API ============

export interface GetTriggersParams {
  page?: number;
  limit?: number;
  status?: string;
  search?: string;
  chat_id?: number;
  sort_by?: 'created_at' | 'key_phrase';
  order?: 'asc' | 'desc';
}

export const triggersApi = {
  getAll: async (params: GetTriggersParams) => {
    const response = await apiClient.get<TriggerListResponse>('/triggers', { params });
    return response.data;
  },

  getQueueStatus: async (id: number) => {
    const response = await apiClient.get<TriggerQueueStatus>(`/triggers/${id}/queue-status`);
    return response.data;
  },

  approve: async (id: number) => {
    const response = await apiClient.post<Trigger>(`/triggers/${id}/approve`);
    return response.data;
  },

  requeue: async (id: number) => {
    const response = await apiClient.post<Trigger>(`/triggers/${id}/requeue`);
    return response.data;
  },

  delete: async (id: number) => {
    const response = await apiClient.delete<{ status: string }>(`/triggers/${id}`);
    return response.data;
  },

  getModerationHistory: async (id: number) => {
    const response = await apiClient.get<ModerationHistoryResponse>(`/triggers/${id}/moderation-history`);
    return response.data;
  },

  streamModerationHistory: (id: number, onMessage: (data: ModerationHistoryItem) => void) => {
    let authData = '';
    let authType = '';
    try {
      const { initDataRaw } = retrieveLaunchParams();
      if (initDataRaw && typeof initDataRaw === 'string') {
        authData = initDataRaw;
        authType = 'twa';
      }
    } catch {
    }
    if (!authData && window.Telegram?.WebApp?.initData) {
      authData = window.Telegram.WebApp.initData;
      authType = 'twa';
    }
    if (!authData) {
      const storedAuth = localStorage.getItem('auth_data');
      if (storedAuth) {
        authData = storedAuth;
        authType = 'widget';
      }
    }

    const baseUrl = import.meta.env.VITE_API_URL || '/api/v1';
    const params = new URLSearchParams();
    if (authData) {
      params.set('auth', authData);
      params.set('auth_type', authType);
    }
    const url = `${baseUrl}/triggers/${id}/moderation-history/stream?${params.toString()}`;

    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ModerationHistoryItem;
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse SSE message:', e);
      }
    };

    eventSource.onerror = (e) => {
      console.error('SSE error:', e);
    };

    return () => eventSource.close();
  },
};

// ============ Users API ============

export interface GetUsersParams {
  page?: number;
  limit?: number;
  query?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  is_premium?: boolean;
  is_trusted?: boolean;
  is_bot_moderator?: boolean;
}

export const usersApi = {
  getAll: async (params: GetUsersParams) => {
    const response = await apiClient.get<PaginatedResponse<User>>('/users', { params });
    return response.data;
  },

  getById: async (id: number) => {
    const response = await apiClient.get<User>(`/users/${id}`);
    return response.data;
  },

  getPhoto: async (id: number) => {
    const response = await apiClient.get(`/users/${id}/photo`, { responseType: 'blob' });
    return response.data;
  },

  updateRole: async (id: number, data: UpdateUserRoleRequest) => {
    const response = await apiClient.post<User>(`/users/${id}/role`, data);
    return response.data;
  },
};

// ============ Chats API ============

export interface GetChatsParams {
  page?: number;
  limit?: number;
  query?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  is_active?: boolean;
  is_trusted?: boolean;
  is_banned?: boolean;
  chat_type?: string;
}

export const chatsApi = {
  getAll: async (params: GetChatsParams) => {
    const response = await apiClient.get<PaginatedResponse<Chat>>('/chats', { params });
    return response.data;
  },

  getById: async (id: number) => {
    const response = await apiClient.get<Chat>(`/chats/${id}`);
    return response.data;
  },

  getPhoto: async (id: number) => {
    const response = await apiClient.get(`/chats/${id}/photo`, { responseType: 'blob' });
    return response.data;
  },

  getUsers: async (id: number, params?: { page?: number; limit?: number }) => {
    const response = await apiClient.get<PaginatedResponse<ChatUser>>(`/chats/${id}/users`, { params });
    return response.data;
  },

  getTriggers: async (id: number, params?: GetTriggersParams) => {
    const response = await apiClient.get<TriggerListResponse>(`/chats/${id}/triggers`, { params });
    return response.data;
  },

  ban: async (id: number, data: BanChatRequest) => {
    const response = await apiClient.post<{ status: string }>(`/chats/${id}/ban`, data);
    return response.data;
  },

  unban: async (id: number) => {
    const response = await apiClient.post<{ status: string }>(`/chats/${id}/unban`);
    return response.data;
  },

  updateSettings: async (id: number, settings: Partial<Chat>) => {
    const response = await apiClient.post<Chat>(`/chats/${id}/settings`, settings);
    return response.data;
  },
};

// ============ Stats API ============

export const statsApi = {
  get: async () => {
    const response = await apiClient.get<StatsResponse>('/stats');
    return response.data;
  },
};

// ============ System API ============

export const systemApi = {
  getConfig: async () => {
    const response = await apiClient.get<{ bot_username: string | null }>('/system/config');
    return response.data;
  },
};

// ============ Media API ============

export const mediaApi = {
  getSticker: async (fileId: string) => {
    const response = await apiClient.get('/media/sticker', {
      params: { file_id: fileId },
      responseType: 'blob',
    });
    return response.data;
  },

  getVideo: async (fileId: string) => {
    const response = await apiClient.get('/media/video', {
      params: { file_id: fileId },
      responseType: 'blob',
    });
    return response.data;
  },
};

// ============ Legacy exports (for backwards compatibility) ============

export const checkCaptcha = captchaApi.check;
export const solveCaptcha = captchaApi.solve;
export const getTriggers = triggersApi.getAll;
export const getTriggerQueueStatus = triggersApi.getQueueStatus;
export const approveTrigger = triggersApi.approve;
export const requeueTrigger = triggersApi.requeue;
export const deleteTrigger = triggersApi.delete;

export default apiClient;
