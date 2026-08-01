import React, { useState, useEffect } from 'react';
import { Play } from 'lucide-react';
import apiClient, { mediaApi } from '../api/client';

interface LazyVideoProps {
  fileId: string;
  fileSize?: number;
  className?: string;
  onClick?: () => void;
  autoPlay?: boolean;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 Б';
  const k = 1024;
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const LazyVideo: React.FC<LazyVideoProps> = ({ fileId, fileSize: initialFileSize, className, onClick, autoPlay = false }) => {
  const [isLoaded, setIsLoaded] = useState(autoPlay);
  const [fileSize, setFileSize] = useState<number | undefined>(initialFileSize);
  const [loadingSize, setLoadingSize] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(() => {
    if (initialFileSize === undefined && !isLoaded && !autoPlay) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
  }, [fileId, initialFileSize, isLoaded, autoPlay]);

  // Видео отдаётся только по подписанному токену (см. media.py) — <video src>
  // не умеет слать Authorization, поэтому URL с токеном строим отдельным запросом.
  useEffect(() => {
    if (!isLoaded) return;
    let cancelled = false;
    mediaApi.getProxyUrl(fileId)
      .then((url) => {
        if (!cancelled) setVideoUrl(url);
      })
      .catch((err) => console.error('Failed to build video URL', err));
    return () => {
      cancelled = true;
    };
  }, [fileId, isLoaded]);

  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.stopPropagation();
      onClick();
    } else {
      setIsLoaded(true);
    }
  };

  if (isLoaded) {
    if (!videoUrl) {
      return (
        <div className={`bg-elevated rounded-lg animate-pulse ${className || 'w-full h-50'}`} />
      );
    }
    return (
      <video
        src={videoUrl}
        controls
        autoPlay={autoPlay}
        className={`rounded-lg ${className || 'max-w-full max-h-75'}`}
        onClick={(e) => e.stopPropagation()}
      />
    );
  }

  return (
    <div
      className={`bg-elevated rounded-lg flex flex-col items-center justify-center cursor-pointer hover:opacity-90 transition-opacity relative ${className || 'w-full h-50'}`}
      onClick={handleClick}
    >
      <div className="bg-black/30 p-3 rounded-full mb-2">
        <Play size={32} className="text-white fill-white" />
      </div>
      <span className="text-hint text-sm font-medium">
        {loadingSize ? 'Вычисление размера…' : fileSize ? formatSize(fileSize) : 'Видео'}
      </span>
    </div>
  );
};

export default LazyVideo;
