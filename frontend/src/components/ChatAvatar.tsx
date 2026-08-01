import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';
import { MessageSquare, X } from 'lucide-react';
import { getCachedAvatarUrl } from '../lib/avatarCache';

interface ChatAvatarProps {
  chatId: number;
  photoId?: string | null;
  className?: string;
}

const ChatAvatar: React.FC<ChatAvatarProps> = ({ chatId, photoId, className = 'w-10 h-10' }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    getCachedAvatarUrl(`chat:${chatId}:${photoId ?? ''}`, async () => {
      const response = await apiClient.get(`/chats/${chatId}/photo`, {
        responseType: 'blob',
      });
      return response.data as Blob;
    }).then((url) => {
      if (!cancelled) setImageUrl(url);
    });

    return () => {
      cancelled = true;
    };
  }, [chatId, photoId]);

  if (!imageUrl) {
    return (
      <div className={`${className} rounded-full bg-elevated flex items-center justify-center text-hint overflow-hidden`}>
        <MessageSquare size={20} />
      </div>
    );
  }

  return (
    <>
      <img
        src={imageUrl}
        alt="Аватар чата"
        className={`${className} rounded-full object-cover cursor-pointer hover:opacity-90 transition-opacity`}
        onClick={(e) => {
            e.stopPropagation();
            setIsModalOpen(true);
        }}
      />

      {isModalOpen && (
        <div
          className="fixed inset-0 z-9999 bg-black/90 flex items-center justify-center p-4 cursor-zoom-out animate-fadeIn"
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
             alt="Аватар чата (полный размер)"
             className="max-w-full max-h-full object-contain rounded-lg shadow-2xl cursor-default"
             onClick={(e) => e.stopPropagation()}
           />
        </div>
      )}
    </>
  );
};

export default ChatAvatar;
