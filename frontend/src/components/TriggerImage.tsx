import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';

interface TriggerImageProps {
  chatId: number;
  triggerId: number;
  alt?: string;
}

const TriggerImage: React.FC<TriggerImageProps> = ({ chatId, triggerId, alt }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

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
      <div style={{
        width: '100%',
        height: '200px',
        backgroundColor: 'var(--secondary-bg-color)',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginTop: '8px'
      }}>
        <span style={{ color: 'var(--hint-color)' }}>Loading image...</span>
      </div>
    );
  }

  if (error || !imageUrl) {
    return (
      <div style={{
        width: '100%',
        height: '100px',
        backgroundColor: 'var(--secondary-bg-color)',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--hint-color)',
        marginTop: '8px'
      }}>
        Image unavailable
      </div>
    );
  }

  return (
    <img
      src={imageUrl}
      alt={alt || 'Trigger content'}
      style={{ maxWidth: '100%', maxHeight: '300px', borderRadius: '8px', marginTop: '8px', objectFit: 'contain' }}
    />
  );
};

export default TriggerImage;
