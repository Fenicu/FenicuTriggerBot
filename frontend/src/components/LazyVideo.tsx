import React, { useState, useEffect } from 'react';
import { Play } from 'lucide-react';
import apiClient from '../api/client';

interface LazyVideoProps {
  fileId: string;
  fileSize?: number;
  className?: string;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const LazyVideo: React.FC<LazyVideoProps> = ({ fileId, fileSize: initialFileSize, className }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [fileSize, setFileSize] = useState<number | undefined>(initialFileSize);
  const [loadingSize, setLoadingSize] = useState(false);

  useEffect(() => {
    if (initialFileSize === undefined && !isLoaded) {
      setLoadingSize(true);
      apiClient.get(`/media/info`, { params: { file_id: fileId } })
        .then(response => {
          setFileSize(response.data.file_size);
        })
        .catch(err => {
          console.error('Failed to fetch video info', err);
        })
        .finally(() => {
          setLoadingSize(false);
        });
    }
  }, [fileId, initialFileSize, isLoaded]);

  if (isLoaded) {
    return (
      <video
        src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${fileId}`}
        controls
        autoPlay
        className={`rounded-lg max-w-full max-h-75 ${className || ''}`}
      />
    );
  }

  return (
    <div
      className={`bg-secondary-bg rounded-lg flex flex-col items-center justify-center cursor-pointer hover:opacity-90 transition-opacity relative ${className || 'w-full h-50'}`}
      onClick={() => setIsLoaded(true)}
    >
      <div className="bg-black/30 p-3 rounded-full mb-2">
        <Play size={32} className="text-white fill-white" />
      </div>
      <span className="text-hint text-sm font-medium">
        {loadingSize ? 'Loading size...' : fileSize ? formatSize(fileSize) : 'Video'}
      </span>
    </div>
  );
};

export default LazyVideo;
