import React, { useEffect, useState } from 'react';
import Lottie from 'lottie-react';
import apiClient from '../api/client';

interface StickerPreviewProps {
  triggerContent: any;
  className?: string;
}

const StickerPreview: React.FC<StickerPreviewProps> = ({ triggerContent, className }) => {
  const [animationData, setAnimationData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fileId = triggerContent.file_id;
  const isVideo = triggerContent.is_video;
  const isAnimated = triggerContent.is_animated;

  useEffect(() => {
    if (isAnimated && fileId) {
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

  if (isVideo) {
    return (
      <video
        src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${fileId}`}
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
          <span className="text-hint text-xs">Loading...</span>
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
      src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${fileId}`}
      alt="Sticker"
      className={`max-w-full max-h-40 object-contain ${className || ''}`}
    />
  );
};

export default StickerPreview;
