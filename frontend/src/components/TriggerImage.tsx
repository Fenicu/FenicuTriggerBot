import React, { useState, useEffect } from 'react';
import { FileText, Mic, Music, Dices } from 'lucide-react';
import LazyVideo from './LazyVideo';
import StickerPreview from './StickerPreview';
import MediaModal from './MediaModal';
import { mediaApi } from '../api/client';

interface TriggerImageProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  trigger: any;
  alt?: string;
  className?: string;
  compact?: boolean;
}

const formatSize = (bytes: number) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes === 0) return '0 Б';
  const k = 1024;
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const TriggerImage: React.FC<TriggerImageProps> = ({ trigger, alt, className, compact = false }) => {
  const [modalContent, setModalContent] = useState<React.ReactNode | null>(null);
  const content = trigger.content;

  // file_id медиа, которому нужен подписанный proxy-URL (см. media.py) — вычисляем
  // ДО раннего return, чтобы useEffect ниже вызывался безусловно на каждом рендере.
  let mediaFileId: string | undefined;
  if (content?.animation) {
    mediaFileId = content.animation.file_id;
  } else if (content?.photo) {
    if (content.photo.file_id) {
      mediaFileId = content.photo.file_id;
    } else if (Array.isArray(content.photo) && content.photo.length > 0) {
      mediaFileId = content.photo[content.photo.length - 1].file_id;
    }
  } else if (content?.voice) {
    mediaFileId = content.voice.file_id;
  } else if (content?.audio) {
    mediaFileId = content.audio.file_id;
  } else if (content?.document?.mime_type?.startsWith('image/')) {
    mediaFileId = content.document.file_id;
  }

  const [mediaUrl, setMediaUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!mediaFileId) {
      return;
    }
    let cancelled = false;
    mediaApi.getProxyUrl(mediaFileId)
      .then((url) => {
        if (!cancelled) setMediaUrl(url);
      })
      .catch((err) => console.error('Failed to build media URL', err));
    return () => {
      cancelled = true;
    };
  }, [mediaFileId]);

  if (!content) return null;

  if (mediaFileId && !mediaUrl) {
    return (
      <div className={`bg-elevated rounded-lg animate-pulse ${className || (compact ? 'w-16 h-16' : 'w-full h-32')}`} />
    );
  }

  const openModal = (node: React.ReactNode) => {
    setModalContent(node);
  };

  const closeModal = () => {
    setModalContent(null);
  };

  // 1. Animation
  if (content.animation) {
    const videoUrl = mediaUrl as string;
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

    const imageUrl = mediaUrl as string;

    return (
      <>
        <img
          src={imageUrl}
          alt={alt || 'Содержимое триггера'}
          className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || (compact ? 'w-16 h-16 mt-0' : 'max-w-full max-h-75 mt-2')}`}
          onClick={(e) => {
            e.stopPropagation();
            openModal(
              <img
                src={imageUrl}
                alt={alt || 'Во весь размер'}
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
      <div className={`flex items-center bg-elevated rounded-lg ${compact ? 'p-1 gap-2 w-full max-w-50' : 'p-3 mt-2'} ${className || ''}`}>
          <div className={`${compact ? 'p-1.5' : 'p-2'} bg-border rounded-full shrink-0`}>
              <Mic size={compact ? 16 : 24} className="text-hint" />
          </div>
          <div className="flex-1 min-w-0">
              <audio
                  src={mediaUrl as string}
                  controls
                  className={`w-full ${compact ? 'h-6' : 'h-8'}`}
              />
              {!compact && (
                  <div className="flex justify-between text-xs text-hint mt-1 px-1">
                      <span>Голосовое сообщение</span>
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
      <div className={`flex ${compact ? 'flex-row items-center gap-2 p-1 max-w-62.5' : 'flex-col p-3 mt-2'} bg-elevated rounded-lg ${className || ''}`}>
          {!compact && (
              <div className="flex items-center mb-2">
                  <div className="bg-border p-2 rounded-full mr-3">
                      <Music size={24} className="text-hint" />
                  </div>
                  <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate text-text">{content.audio.title || 'Неизвестный трек'}</p>
                      <p className="text-xs text-hint truncate">{content.audio.performer || 'Неизвестный исполнитель'}</p>
                  </div>
              </div>
          )}
          {compact && (
             <div className="bg-border p-1.5 rounded-full shrink-0">
                <Music size={16} className="text-hint" />
             </div>
          )}
          <audio
              src={mediaUrl as string}
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
       const imageUrl = mediaUrl as string;

       return (
        <>
          <img
            src={imageUrl}
            alt={file_name || alt || 'Содержимое документа'}
            className={`rounded-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${className || (compact ? 'w-16 h-16 mt-0' : 'max-w-full max-h-75 mt-2')}`}
            onClick={(e) => {
              e.stopPropagation();
              openModal(
                <img
                  src={imageUrl}
                  alt={file_name || alt || 'Во весь размер'}
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
      <div className={`flex items-center bg-elevated rounded-lg ${compact ? 'p-1 gap-2' : 'p-3 mt-2'} ${className || ''}`}>
        <div className={`${compact ? 'p-1.5' : 'p-2'} bg-border rounded-full shrink-0`}>
          <FileText size={compact ? 16 : 24} className="text-hint" />
        </div>
        <div className="flex-1 min-w-0">
          <p className={`font-medium truncate text-text ${compact ? 'text-xs' : 'text-sm'}`}>{file_name || 'Документ'}</p>
          {!compact && file_size && <p className="text-xs text-hint">{formatSize(file_size)}</p>}
        </div>
      </div>
    );
  }

  // 8. Dice
  if (content.dice) {
    return (
      <div className={`flex items-center bg-elevated rounded-lg ${compact ? 'p-1 gap-2 w-full max-w-50' : 'p-3 mt-2'} ${className || ''}`}>
          <div className={`${compact ? 'p-1.5' : 'p-2'} bg-border rounded-full shrink-0`}>
              <Dices size={compact ? 16 : 24} className="text-hint" />
          </div>
          <div className="flex-1 min-w-0">
              <p className={`font-medium truncate text-text ${compact ? 'text-xs' : 'text-sm'}`}>
                {content.dice.emoji} {content.dice.value ? `(Значение: ${content.dice.value})` : ''}
              </p>
              {!compact && <p className="text-xs text-hint">Бросок кубика</p>}
          </div>
      </div>
    );
  }

  return null;
};

export default TriggerImage;
