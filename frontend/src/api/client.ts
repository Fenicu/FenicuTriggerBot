import axios, { type InternalAxiosRequestConfig } from 'axios';
import { retrieveLaunchParams } from '@telegram-apps/sdk-react';

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
  }
  console.log(`[API] Requesting: ${config.baseURL}${config.url}`);
  return config;
});

export default apiClient;
