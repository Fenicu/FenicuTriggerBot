import React, { useEffect, useState } from 'react';
import Lottie from 'lottie-react';
import apiClient, { mediaApi } from '../api/client';

interface StickerPreviewProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  triggerContent: any;
  className?: string;
}

const StickerPreview: React.FC<StickerPreviewProps> = ({ triggerContent, className }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [animationData, setAnimationData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);

  const fileId = triggerContent.file_id;
  const isVideo = triggerContent.is_video;
  const isAnimated = triggerContent.is_animated;

  useEffect(() => {
    if (isAnimated && fileId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(true);
      apiClient.get(`/media/proxy`, { params: { file_id: fileId } })
        .then(response => {
          setAnimationData(response.data);
        })
        .catch(err => {
          console.error('Failed to load sticker animation', err);
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [fileId, isAnimated]);

  // Статичный/видео-стикер отдаётся напрямую через <video>/<img> src — токен на
  // file_id нужен получить отдельным авторизованным запросом (см. media.py).
  useEffect(() => {
    if (isAnimated || !fileId) return;
    let cancelled = false;
    mediaApi.getProxyUrl(fileId)
      .then((url) => {
        if (!cancelled) setMediaUrl(url);
      })
      .catch((err) => console.error('Failed to build sticker URL', err));
    return () => {
      cancelled = true;
    };
  }, [fileId, isAnimated]);

  if (!isAnimated && !mediaUrl) {
    return (
      <div className={`flex items-center justify-center ${className || 'w-32 h-32'}`}>
        <span className="text-hint text-xs">Загрузка…</span>
      </div>
    );
  }

  if (isVideo) {
    return (
      <video
        src={mediaUrl ?? undefined}
        loop
        autoPlay
        muted
        playsInline
        className={`max-w-full max-h-40 object-contain ${className || ''}`}
      />
    );
  }

  if (isAnimated) {
    if (loading || !animationData) {
       return (
        <div className={`flex items-center justify-center ${className || 'w-32 h-32'}`}>
          <span className="text-hint text-xs">Загрузка…</span>
        </div>
      );
    }
    return (
      <div className={`max-w-full max-h-40 ${className || 'w-32 h-32'}`}>
        <Lottie animationData={animationData} loop={true} />
      </div>
    );
  }

  return (
    <img
      src={mediaUrl ?? undefined}
      alt="Стикер"
      className={`max-w-full max-h-40 object-contain ${className || ''}`}
    />
  );
};

export default StickerPreview;
