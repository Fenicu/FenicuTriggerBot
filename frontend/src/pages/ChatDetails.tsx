import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat } from '../types';
import { ArrowLeft } from 'lucide-react';

const ChatDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [chat, setChat] = useState<Chat | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const fetchChat = async () => {
      try {
        const res = await apiClient.get<Chat>(`/chats/${id}`);
        setChat(res.data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchChat();
  }, [id]);

  const toggleTrust = async () => {
    if (!chat) return;
    try {
      const res = await apiClient.post<Chat>(`/chats/${id}/trust`);
      setChat(res.data);
    } catch (error) {
      console.error(error);
      alert('Failed to toggle trust');
    }
  };

  const banChat = async () => {
    const reason = prompt('Enter ban reason:');
    if (!reason) return;
    try {
      const res = await apiClient.post<Chat>(`/chats/${id}/ban`, { reason });
      setChat(res.data);
    } catch (error) {
      console.error(error);
      alert('Failed to ban chat');
    }
  };

  const leaveChat = async () => {
    if (!confirm('Are you sure you want the bot to leave this chat?')) return;
    try {
      await apiClient.post(`/chats/${id}/leave`);
      alert('Bot left the chat');
      navigate('/chats');
    } catch (error) {
      console.error(error);
      alert('Failed to leave chat');
    }
  };

  const sendMessage = async () => {
    if (!message.trim()) return;
    try {
      await apiClient.post(`/chats/${id}/message`, { text: message });
      setMessage('');
      alert('Message sent');
    } catch (error) {
      console.error(error);
      alert('Failed to send message');
    }
  };

  if (loading) return <div style={{ padding: '16px' }}>Loading...</div>;
  if (!chat) return <div style={{ padding: '16px' }}>Chat not found</div>;

  return (
    <div style={{ padding: '16px' }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', color: 'var(--link-color)' }}>
        <ArrowLeft size={20} style={{ marginRight: '4px' }} /> Back
      </button>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 'bold' }}>Chat {chat.id}</h1>
        <p style={{ color: 'var(--hint-color)' }}>Language: {chat.language_code}</p>
        <p style={{ color: 'var(--hint-color)' }}>Warn Limit: {chat.warn_limit}</p>
        {chat.is_banned && <p style={{ color: '#ef4444', marginTop: '8px' }}>Banned: {chat.ban_reason}</p>}
      </div>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', overflow: 'hidden', marginBottom: '16px' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--secondary-bg-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Trusted</span>
          <input
            type="checkbox"
            checked={chat.is_trusted}
            onChange={toggleTrust}
            style={{ transform: 'scale(1.2)' }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <button
            onClick={banChat}
            style={{ backgroundColor: '#ef4444', color: 'white', padding: '12px', borderRadius: '12px', fontWeight: 'bold' }}
        >
            Ban Chat
        </button>
        <button
            onClick={leaveChat}
            style={{ backgroundColor: 'var(--section-bg-color)', color: '#ef4444', padding: '12px', borderRadius: '12px', fontWeight: 'bold' }}
        >
            Leave Chat
        </button>
      </div>

      <div style={{ marginTop: '24px' }}>
        <h3 style={{ marginBottom: '8px' }}>Send Message</h3>
        <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '8px', border: '1px solid var(--hint-color)', minHeight: '80px' }}
            placeholder="Type a message..."
        />
        <button
            onClick={sendMessage}
            style={{ backgroundColor: 'var(--button-color)', color: 'var(--button-text-color)', padding: '12px', borderRadius: '12px', width: '100%', marginTop: '8px', fontWeight: 'bold' }}
        >
            Send
        </button>
      </div>
    </div>
  );
};

export default ChatDetails;
