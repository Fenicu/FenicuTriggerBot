import { useRef, useState } from 'react';
import { chatsApi } from '../api/client';
import { toast } from '../store/store';

interface MediaUploadProps {
  chatId: number;
  media: { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null;
  onMediaChange: (media: { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null) => void;
}

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'video/mp4', 'image/gif'];
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

function getFileTypeIcon(file_type: 'photo' | 'video' | 'animation'): string {
  if (file_type === 'photo') return '📷';
  if (file_type === 'video') return '🎬';
  return '🎞';
}

function getFileTypeLabel(file_type: 'photo' | 'video' | 'animation'): string {
  if (file_type === 'photo') return 'Фото';
  if (file_type === 'video') return 'Видео';
  return 'GIF';
}

export function MediaUpload({ chatId, media, onMediaChange }: MediaUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  async function handleFile(file: File) {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      toast.error('Неподдерживаемый тип файла. Разрешены: JPG, PNG, MP4, GIF');
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      toast.error('Файл слишком большой. Максимальный размер — 10 МБ');
      return;
    }

    setIsUploading(true);
    try {
      const result = await chatsApi.uploadWelcomeMedia(chatId, file);
      onMediaChange({ file_id: result.file_id, file_type: result.file_type });
    } catch {
      // error toast is handled by the api interceptor
    } finally {
      setIsUploading(false);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // reset so the same file can be selected again
    e.target.value = '';
  }

  if (isUploading) {
    return (
      <div className="border-2 border-dashed rounded-xl p-6 text-center border-border">
        <div className="text-hint text-sm">Загрузка...</div>
      </div>
    );
  }

  if (media) {
    return (
      <div className="flex items-center justify-between bg-elevated rounded-xl p-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">{getFileTypeIcon(media.file_type)}</span>
          <span className="text-sm">{getFileTypeLabel(media.file_type)}</span>
        </div>
        <button
          onClick={() => onMediaChange(null)}
          className="text-red-500 hover:bg-red-500/10 p-1 rounded"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
        isDragging ? 'border-link bg-link/10' : 'border-border hover:border-button'
      }`}
    >
      <div className="text-3xl mb-2">📷</div>
      <div className="text-hint text-sm">Перетащите фото, видео или GIF</div>
      <div className="text-hint text-xs mt-1">JPG, PNG, MP4, GIF · до 10 МБ</div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,video/mp4,image/gif"
        className="hidden"
        onChange={handleFileSelect}
      />
    </div>
  );
}

export default MediaUpload;
