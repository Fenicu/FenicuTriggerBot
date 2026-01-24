import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';
import { User, X } from 'lucide-react';

interface UserAvatarProps {
  userId: number;
  photoId?: string | null;
  className?: string;
}

const UserAvatar: React.FC<UserAvatarProps> = ({ userId, photoId, className = 'w-10 h-10' }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    const fetchImage = async () => {
      try {
        const response = await apiClient.get(`/users/${userId}/photo`, {
          responseType: 'blob',
        });
        objectUrl = URL.createObjectURL(response.data);
        setImageUrl(objectUrl);
      } catch (err) {
        // Silent fail for users without photos
      }
    };

    fetchImage();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [userId, photoId]);

  if (!imageUrl) {
    return (
      <div className={`${className} rounded-full bg-secondary-bg flex items-center justify-center text-hint overflow-hidden`}>
        <User size={20} />
      </div>
    );
  }

  return (
    <>
      <img
        src={imageUrl}
        alt="User Avatar"
        className={`${className} rounded-full object-cover cursor-pointer hover:opacity-90 transition-opacity`}
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
             alt="User Avatar Full"
             className="max-w-full max-h-full object-contain rounded-lg shadow-2xl cursor-default"
             onClick={(e) => e.stopPropagation()}
           />
        </div>
      )}
    </>
  );
};

export default UserAvatar;
