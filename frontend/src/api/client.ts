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

export default apiClient;
