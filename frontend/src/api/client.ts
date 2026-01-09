import axios, { type InternalAxiosRequestConfig } from 'axios';
import { retrieveLaunchParams } from '@telegram-apps/sdk-react';

const apiClient = axios.create({
  baseURL: '/api/v1',
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  try {
    const { initDataRaw } = retrieveLaunchParams();
    if (initDataRaw) {
      config.headers.set('Authorization', `twa-init-data ${initDataRaw}`);
    }
  } catch (e) {
    // console.warn('Failed to retrieve launch params (running outside Telegram?)', e);
  }
  return config;
});

export default apiClient;
