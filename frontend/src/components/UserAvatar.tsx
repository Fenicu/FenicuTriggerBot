import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';
import { User } from 'lucide-react';

interface UserAvatarProps {
  userId: number;
  photoId?: string | null;
  className?: string;
}

const UserAvatar: React.FC<UserAvatarProps> = ({ userId, photoId, className = 'w-10 h-10' }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photoId) return;

    let objectUrl: string | null = null;
    const fetchImage = async () => {
      try {
        const response = await apiClient.get(`/users/${userId}/photo`, {
          responseType: 'blob',
        });
        objectUrl = URL.createObjectURL(response.data);
        setImageUrl(objectUrl);
      } catch (err) {
        console.error('Failed to load user avatar', err);
      }
    };

    fetchImage();

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [userId, photoId]);

  if (!photoId || !imageUrl) {
    return (
      <div className={`${className} rounded-full bg-secondary-bg flex items-center justify-center text-hint overflow-hidden`}>
        <User size={20} />
      </div>
    );
  }

  return (
    <img
      src={imageUrl}
      alt="User Avatar"
      className={`${className} rounded-full object-cover`}
    />
  );
};

export default UserAvatar;
