import React from 'react';
import { useParams } from 'react-router-dom';
import ChatSettingsForm from '../components/ChatSettingsForm';

const ChatSettings: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();

  if (!chatId) {
    return <div className="p-4 text-center text-hint">Chat ID not provided</div>;
  }

  const parsedId = parseInt(chatId);
  if (isNaN(parsedId)) {
    return <div className="p-4 text-center text-hint">Invalid Chat ID</div>;
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="max-w-lg mx-auto">
        <ChatSettingsForm chatId={parsedId} />
      </div>
    </div>
  );
};

export default ChatSettings;
