import React, { useState } from 'react';
import { X } from 'lucide-react';
import LazyVideo from './LazyVideo';
import StickerPreview from './StickerPreview';

interface TriggerImageProps {
  trigger: any;
  alt?: string;
  className?: string;
}

const TriggerImage: React.FC<TriggerImageProps> = ({ trigger, alt, className }) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const content = trigger.content;

  if (!content) return null;

  if (content.video) {
    return (
      <LazyVideo
        fileId={content.video.file_id}
        fileSize={content.video.file_size}
        className={className}
      />
    );
  }

  if (content.sticker) {
    return (
      <StickerPreview
        triggerContent={content.sticker}
        className={className}
      />
    );
  }

  if (content.animation) {
     return (
      <LazyVideo
        fileId={content.animation.file_id}
        fileSize={content.animation.file_size}
        className={className}
      />
    );
  }

  if (content.photo) {
    let fileId = null;

    if (content.photo.file_id) {
      fileId = content.photo.file_id;
    } else if (Array.isArray(content.photo) && content.photo.length > 0) {
      fileId = content.photo[content.photo.length - 1].file_id;
    }

    if (!fileId) return null;

    const imageUrl = `${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${fileId}`;

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
            className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4 cursor-zoom-out animate-in fade-in duration-200"
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
  }

  return null;
};

export default TriggerImage;
