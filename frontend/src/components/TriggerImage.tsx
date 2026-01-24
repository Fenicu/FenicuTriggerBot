import React, { useState } from 'react';
import { X, FileText, Mic, Music } from 'lucide-react';
import LazyVideo from './LazyVideo';
import StickerPreview from './StickerPreview';

interface TriggerImageProps {
  trigger: any;
  alt?: string;
  className?: string;
}

const formatSize = (bytes: number) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const TriggerImage: React.FC<TriggerImageProps> = ({ trigger, alt, className }) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const content = trigger.content;

  if (!content) return null;

  // 1. Animation
  if (content.animation) {
    return (
      <video
        src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.animation.file_id}`}
        loop
        autoPlay
        muted
        playsInline
        className={`rounded-lg object-contain ${className || 'max-w-full max-h-75'}`}
      />
    );
  }

  // 2. Video
  if (content.video) {
    return (
      <LazyVideo
        fileId={content.video.file_id}
        fileSize={content.video.file_size}
        className={className}
      />
    );
  }

  // 3. Sticker
  if (content.sticker) {
    return (
      <StickerPreview
        triggerContent={content.sticker}
        className={className}
      />
    );
  }

  // 4. Photo
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

  // 5. Voice
  if (content.voice) {
    return (
      <div className={`flex items-center p-3 bg-secondary-bg rounded-lg ${className || 'mt-2'}`}>
          <div className="bg-purple-500/20 p-2 rounded-full mr-3">
              <Mic size={24} className="text-purple-500" />
          </div>
          <div className="flex-1 min-w-0">
              <audio
                  src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.voice.file_id}`}
                  controls
                  className="w-full h-8"
              />
              <div className="flex justify-between text-xs text-hint mt-1 px-1">
                  <span>Voice Message</span>
                  {content.voice.duration && <span>{content.voice.duration}s</span>}
              </div>
          </div>
      </div>
    );
  }

  // 6. Audio
  if (content.audio) {
    return (
      <div className={`flex flex-col p-3 bg-secondary-bg rounded-lg ${className || 'mt-2'}`}>
          <div className="flex items-center mb-2">
              <div className="bg-orange-500/20 p-2 rounded-full mr-3">
                  <Music size={24} className="text-orange-500" />
              </div>
              <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate text-white">{content.audio.title || 'Unknown Track'}</p>
                  <p className="text-xs text-hint truncate">{content.audio.performer || 'Unknown Artist'}</p>
              </div>
          </div>
          <audio
              src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.audio.file_id}`}
              controls
              className="w-full h-8"
          />
      </div>
    );
  }

  // 7. Document
  if (content.document) {
    const { file_id, file_name, mime_type, file_size } = content.document;

    // Video Document
    if (mime_type?.startsWith('video/')) {
      return (
        <LazyVideo
          fileId={file_id}
          fileSize={file_size}
          className={className}
        />
      );
    }

    // Image Document
    if (mime_type?.startsWith('image/')) {
       const imageUrl = `${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${file_id}`;

       return (
        <>
          <img
            src={imageUrl}
            alt={file_name || alt || 'Document content'}
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
                 alt={file_name || alt || 'Full size'}
                 className="max-w-full max-h-full object-contain rounded-lg shadow-2xl cursor-default"
                 onClick={(e) => e.stopPropagation()}
               />
            </div>
          )}
        </>
       );
    }

    // Generic Document
    return (
      <div className={`flex items-center p-3 bg-secondary-bg rounded-lg ${className || 'mt-2'}`}>
        <div className="bg-blue-500/20 p-2 rounded-full mr-3">
          <FileText size={24} className="text-blue-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate text-white">{file_name || 'Document'}</p>
          {file_size && <p className="text-xs text-hint">{formatSize(file_size)}</p>}
        </div>
      </div>
    );
  }

  return null;
};

export default TriggerImage;
