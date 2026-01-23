import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';
import { X } from 'lucide-react';

interface TriggerImageProps {
  chatId: number;
  triggerId: number;
  alt?: string;
  className?: string;
}

const TriggerImage: React.FC<TriggerImageProps> = ({ chatId, triggerId, alt, className }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;

    const fetchImage = async () => {
      try {
        const response = await apiClient.get(`/chats/${chatId}/triggers/${triggerId}/image`, {
          responseType: 'blob',
        });
        objectUrl = URL.createObjectURL(response.data);
        setImageUrl(objectUrl);
      } catch (err) {
        console.error('Failed to load trigger image', err);
        setError(true);
      } finally {
        setLoading(false);
      }
    };

    fetchImage();

    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [chatId, triggerId]);

  if (loading) {
    return (
      <div className={`bg-secondary-bg rounded-lg flex items-center justify-center ${className || 'w-full h-50 mt-2'}`}>
        <span className="text-hint text-xs">Loading...</span>
      </div>
    );
  }

  if (error || !imageUrl) {
    return (
      <div className={`bg-secondary-bg rounded-lg flex items-center justify-center text-hint ${className || 'w-full h-25 mt-2'}`}>
        <span className="text-xs">Unavailable</span>
      </div>
    );
  }

  return (
    <>
      <img
        src={imageUrl}
        alt={alt || 'Trigger content'}
        className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || 'max-w-full max-h-75 mt-2'}`}
        onClick={(e) => {
          e.stopPropagation();
          setIsModalOpen(true);
        }}
      />

      {isModalOpen && (
        <div
          className="fixed inset-0 z-9999 bg-black/90 flex items-center justify-center p-4 cursor-zoom-out animate-in fade-in duration-200"
          onClick={(e) => {
             e.stopPropagation();
             setIsModalOpen(false);
          }}
        >
           <button
             className="absolute top-4 right-4 text-white/70 hover:text-white transition-colors"
             onClick={() => setIsModalOpen(false)}
           >
             <X size={32} />
           </button>
           <img
             src={imageUrl}
             alt={alt || 'Full size'}
             className="max-w-full max-h-full object-contain rounded-lg shadow-2xl cursor-default"
             onClick={(e) => e.stopPropagation()}
           />
        </div>
      )}
    </>
  );
};

export default TriggerImage;
