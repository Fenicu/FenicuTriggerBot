import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import ChatSettingsForm from '../components/ChatSettingsForm';
import { useTelegramBackButton } from '../hooks/useTelegramBackButton';

const ChatSettings: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();
  // Нативная кнопка "Назад" Telegram -- страница деталей
  useTelegramBackButton(() => navigate(-1));

  if (!chatId) {
    return <div className="p-4 text-center text-hint">ID чата не указан</div>;
  }

  const parsedId = parseInt(chatId);
  if (isNaN(parsedId)) {
    return <div className="p-4 text-center text-hint">Некорректный ID чата</div>;
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur-[12px] px-4 py-3 border-b border-border">
        <div className="max-w-lg mx-auto flex items-center gap-2.5">
          <button onClick={() => navigate(-1)} className="text-button p-1">
            <ArrowLeft size={20} />
          </button>
          <span className="text-[17px] font-semibold">Настройки чата</span>
        </div>
      </div>
      <div className="max-w-lg mx-auto p-4">
        <ChatSettingsForm chatId={parsedId} />
      </div>
    </div>
  );
};

export default ChatSettings;
