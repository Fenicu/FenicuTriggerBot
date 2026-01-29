import React, { useState } from 'react';
import { FileText, Mic, Music, Dices } from 'lucide-react';
import LazyVideo from './LazyVideo';
import StickerPreview from './StickerPreview';
import MediaModal from './MediaModal';

interface TriggerImageProps {
  trigger: any;
  alt?: string;
  className?: string;
  compact?: boolean;
}

const formatSize = (bytes: number) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const TriggerImage: React.FC<TriggerImageProps> = ({ trigger, alt, className, compact = false }) => {
  const [modalContent, setModalContent] = useState<React.ReactNode | null>(null);
  const content = trigger.content;

  if (!content) return null;

  const openModal = (node: React.ReactNode) => {
    setModalContent(node);
  };

  const closeModal = () => {
    setModalContent(null);
  };

  // 1. Animation
  if (content.animation) {
    const videoUrl = `${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.animation.file_id}`;
    return (
      <>
        <video
          src={videoUrl}
          loop
          autoPlay
          muted
          playsInline
          className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || (compact ? 'w-16 h-16' : 'max-w-full max-h-75')}`}
          onClick={(e) => {
            e.stopPropagation();
            openModal(
              <video
                src={videoUrl}
                loop
                autoPlay
                muted
                playsInline
                controls
                className="max-w-full max-h-[90vh] rounded-lg shadow-2xl"
              />
            );
          }}
        />
        <MediaModal isOpen={!!modalContent} onClose={closeModal}>
          {modalContent}
        </MediaModal>
      </>
    );
  }

  // 2. Video
  if (content.video) {
    return (
      <>
        <LazyVideo
          fileId={content.video.file_id}
          fileSize={content.video.file_size}
          className={className || (compact ? 'w-16 h-16' : undefined)}
          onClick={() => {
            openModal(
              <LazyVideo
                fileId={content.video.file_id}
                fileSize={content.video.file_size}
                autoPlay={true}
                className="max-w-full max-h-[90vh]"
              />
            );
          }}
        />
        <MediaModal isOpen={!!modalContent} onClose={closeModal}>
          {modalContent}
        </MediaModal>
      </>
    );
  }

  // 2.1 Video Note
  if (content.video_note) {
    return (
      <>
        <LazyVideo
          fileId={content.video_note.file_id}
          fileSize={content.video_note.file_size}
          className={`${className || (compact ? 'w-16 h-16' : 'w-64 h-64')} rounded-full aspect-square object-cover`}
          onClick={() => {
            openModal(
              <LazyVideo
                fileId={content.video_note.file_id}
                fileSize={content.video_note.file_size}
                autoPlay={true}
                className="max-w-[90vh] max-h-[90vh] rounded-full aspect-square object-cover"
              />
            );
          }}
        />
        <MediaModal isOpen={!!modalContent} onClose={closeModal}>
          {modalContent}
        </MediaModal>
      </>
    );
  }

  // 3. Sticker
  if (content.sticker) {
    return (
      <>
        <div
            onClick={(e) => {
                e.stopPropagation();
                openModal(
                    <StickerPreview
                        triggerContent={content.sticker}
                        className="max-w-full max-h-[80vh] w-96 h-96"
                    />
                );
            }}
            className="cursor-pointer hover:opacity-90 transition-opacity inline-block"
        >
            <StickerPreview
                triggerContent={content.sticker}
                className={className || (compact ? 'w-16 h-16' : undefined)}
            />
        </div>
        <MediaModal isOpen={!!modalContent} onClose={closeModal}>
          {modalContent}
        </MediaModal>
      </>
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
          className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || (compact ? 'w-16 h-16 mt-0' : 'max-w-full max-h-75 mt-2')}`}
          onClick={(e) => {
            e.stopPropagation();
            openModal(
              <img
                src={imageUrl}
                alt={alt || 'Full size'}
                className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
              />
            );
          }}
        />
        <MediaModal isOpen={!!modalContent} onClose={closeModal}>
          {modalContent}
        </MediaModal>
      </>
    );
  }

  // 5. Voice
  if (content.voice) {
    return (
      <div className={`flex items-center bg-secondary-bg rounded-lg ${compact ? 'p-1 gap-2 w-full max-w-50' : 'p-3 mt-2'} ${className || ''}`}>
          <div className={`${compact ? 'p-1.5' : 'p-2'} bg-purple-500/20 rounded-full shrink-0`}>
              <Mic size={compact ? 16 : 24} className="text-purple-500" />
          </div>
          <div className="flex-1 min-w-0">
              <audio
                  src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.voice.file_id}`}
                  controls
                  className={`w-full ${compact ? 'h-6' : 'h-8'}`}
              />
              {!compact && (
                  <div className="flex justify-between text-xs text-hint mt-1 px-1">
                      <span>Voice Message</span>
                      {content.voice.duration && <span>{content.voice.duration}s</span>}
                  </div>
              )}
          </div>
      </div>
    );
  }

  // 6. Audio
  if (content.audio) {
    return (
      <div className={`flex ${compact ? 'flex-row items-center gap-2 p-1 max-w-62.5' : 'flex-col p-3 mt-2'} bg-secondary-bg rounded-lg ${className || ''}`}>
          {!compact && (
              <div className="flex items-center mb-2">
                  <div className="bg-orange-500/20 p-2 rounded-full mr-3">
                      <Music size={24} className="text-orange-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate text-white">{content.audio.title || 'Unknown Track'}</p>
                      <p className="text-xs text-hint truncate">{content.audio.performer || 'Unknown Artist'}</p>
                  </div>
              </div>
          )}
          {compact && (
             <div className="bg-orange-500/20 p-1.5 rounded-full shrink-0">
                <Music size={16} className="text-orange-500" />
             </div>
          )}
          <audio
              src={`${import.meta.env.VITE_API_URL || '/api/v1'}/media/proxy?file_id=${content.audio.file_id}`}
              controls
              className={`w-full ${compact ? 'h-6' : 'h-8'}`}
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
        <>
            <LazyVideo
            fileId={file_id}
            fileSize={file_size}
            className={className || (compact ? 'w-16 h-16' : undefined)}
            onClick={() => {
                openModal(
                <LazyVideo
                    fileId={file_id}
                    fileSize={file_size}
                    autoPlay={true}
                    className="max-w-full max-h-[90vh]"
                />
                );
            }}
            />
            <MediaModal isOpen={!!modalContent} onClose={closeModal}>
                {modalContent}
            </MediaModal>
        </>
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
            className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || (compact ? 'w-16 h-16 mt-0' : 'max-w-full max-h-75 mt-2')}`}
            onClick={(e) => {
              e.stopPropagation();
              openModal(
                <img
                  src={imageUrl}
                  alt={file_name || alt || 'Full size'}
                  className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
                  onClick={(e) => e.stopPropagation()}
                />
              );
            }}
          />
          <MediaModal isOpen={!!modalContent} onClose={closeModal}>
            {modalContent}
          </MediaModal>
        </>
       );
    }

    // Generic Document
    return (
      <div className={`flex items-center bg-secondary-bg rounded-lg ${compact ? 'p-1 gap-2' : 'p-3 mt-2'} ${className || ''}`}>
        <div className={`${compact ? 'p-1.5' : 'p-2'} bg-blue-500/20 rounded-full shrink-0`}>
          <FileText size={compact ? 16 : 24} className="text-blue-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className={`font-medium truncate text-white ${compact ? 'text-xs' : 'text-sm'}`}>{file_name || 'Document'}</p>
          {!compact && file_size && <p className="text-xs text-hint">{formatSize(file_size)}</p>}
        </div>
      </div>
    );
  }

  // 8. Dice
  if (content.dice) {
    return (
      <div className={`flex items-center bg-secondary-bg rounded-lg ${compact ? 'p-1 gap-2 w-full max-w-50' : 'p-3 mt-2'} ${className || ''}`}>
          <div className={`${compact ? 'p-1.5' : 'p-2'} bg-red-500/20 rounded-full shrink-0`}>
              <Dices size={compact ? 16 : 24} className="text-red-500" />
          </div>
          <div className="flex-1 min-w-0">
              <p className={`font-medium truncate text-white ${compact ? 'text-xs' : 'text-sm'}`}>
                {content.dice.emoji} {content.dice.value ? `(Value: ${content.dice.value})` : ''}
              </p>
              {!compact && <p className="text-xs text-hint">Dice Roll</p>}
          </div>
      </div>
    );
  }

  return null;
};

export default TriggerImage;
