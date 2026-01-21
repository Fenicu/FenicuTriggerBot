import axios, { type InternalAxiosRequestConfig } from 'axios';
import { retrieveLaunchParams } from '@telegram-apps/sdk-react';
import type { CaptchaResponse, Trigger, TriggerListResponse, TriggerQueueStatus } from '../types';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  let initData = '';
  try {
    const { initDataRaw } = retrieveLaunchParams();
    if (initDataRaw && typeof initDataRaw === 'string') {
      initData = initDataRaw;
    }
  } catch (e) {
    console.warn('Failed to retrieve launch params via SDK:', e);
  }

  if (!initData && (window as any).Telegram?.WebApp?.initData) {
    initData = (window as any).Telegram.WebApp.initData;
  }

  if (initData) {
    config.headers.set('Authorization', `twa-init-data ${initData}`);
  } else {
    const storedAuth = localStorage.getItem('auth_data');
    if (storedAuth) {
      config.headers.set('Authorization', `login-widget-data ${storedAuth}`);
    }
  }
  console.log(`[API] Requesting: ${config.baseURL}${config.url}`);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login if unauthorized and not already there
      if (!window.location.hash.includes('#/login')) {
        window.location.hash = '#/login';
      }
    }
    return Promise.reject(error);
  }
);

export const checkCaptcha = async (initData?: string) => {
  const config = initData ? { headers: { Authorization: `twa-init-data ${initData}` } } : {};
  const response = await apiClient.get<CaptchaResponse>('/captcha/check', config);
  return response.data;
};

export const solveCaptcha = async (initData?: string) => {
  const config = initData ? { headers: { Authorization: `twa-init-data ${initData}` } } : {};
  const response = await apiClient.post<{ ok: boolean }>('/captcha/solve', {}, config);
  return response.data;
};

export const getTriggers = async (params: {
  page?: number;
  limit?: number;
  status?: string;
  search?: string;
  chat_id?: number;
}) => {
  const response = await apiClient.get<TriggerListResponse>('/triggers', { params });
  return response.data;
};

export const getTriggerQueueStatus = async (id: number) => {
  const response = await apiClient.get<TriggerQueueStatus>(`/triggers/${id}/queue-status`);
  return response.data;
};

export const approveTrigger = async (id: number) => {
  const response = await apiClient.post<Trigger>(`/triggers/${id}/approve`);
  return response.data;
};

export const requeueTrigger = async (id: number) => {
  const response = await apiClient.post<Trigger>(`/triggers/${id}/requeue`);
  return response.data;
};

export const deleteTrigger = async (id: number) => {
  const response = await apiClient.delete<{ status: string }>(`/triggers/${id}`);
  return response.data;
};

export default apiClient;
