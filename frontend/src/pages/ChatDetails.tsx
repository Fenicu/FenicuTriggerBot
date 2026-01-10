import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat } from '../types';
import { ArrowLeft, ExternalLink, Shield, AlertTriangle, MessageSquare, Info, Settings, Zap } from 'lucide-react';
import Toast from '../components/Toast';

const InfoRow = ({ label, value }: { label: string, value: React.ReactNode }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--secondary-bg-color)' }}>
    <span style={{ color: 'var(--hint-color)' }}>{label}</span>
    <span style={{ fontWeight: '500', textAlign: 'right' }}>{value}</span>
  </div>
);

const Section = ({ title, icon: Icon, children }: { title: string, icon: React.ElementType, children: React.ReactNode }) => (
  <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: '12px', color: 'var(--link-color)' }}>
      <Icon size={20} style={{ marginRight: '8px' }} />
      <h2 style={{ fontSize: '16px', fontWeight: 'bold', margin: 0 }}>{title}</h2>
    </div>
    {children}
  </div>
);

const ChatDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [chat, setChat] = useState<Chat | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

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

  useEffect(() => {
    if (chat?.photo_id) {
      apiClient.get(`/chats/${chat.id}/photo`, { responseType: 'blob' })
        .then(res => {
          const url = URL.createObjectURL(res.data);
          setAvatarUrl(url);
        })
        .catch(err => console.error('Failed to load avatar', err));
    } else {
      setAvatarUrl(null);
    }
  }, [chat]);

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
      setToastMessage('Message sent');
    } catch (error) {
      console.error(error);
      alert('Failed to send message');
    }
  };

  if (loading) return <div style={{ padding: '16px' }}>Loading...</div>;
  if (!chat) return <div style={{ padding: '16px' }}>Chat not found</div>;

  return (
    <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', color: 'var(--link-color)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}>
        <ArrowLeft size={20} style={{ marginRight: '4px' }} /> Back
      </button>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '20px', marginBottom: '16px', textAlign: 'center' }}>
        {avatarUrl && (
          <img
            src={avatarUrl}
            alt="Chat Avatar"
            style={{ width: '80px', height: '80px', borderRadius: '50%', objectFit: 'cover', marginBottom: '12px' }}
          />
        )}
        <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>
          {chat.title || chat.username || `Chat ${chat.id}`}
        </h1>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', flexWrap: 'wrap' }}>
            {chat.type && (
                <span style={{ backgroundColor: 'var(--secondary-bg-color)', padding: '4px 8px', borderRadius: '6px', fontSize: '14px', textTransform: 'capitalize' }}>
                    {chat.type}
                </span>
            )}
            <span style={{ backgroundColor: 'var(--secondary-bg-color)', padding: '4px 8px', borderRadius: '6px', fontSize: '14px' }}>
                ID: {chat.id}
            </span>
        </div>
        {chat.is_banned && (
            <div style={{ marginTop: '12px', color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '8px', borderRadius: '8px' }}>
                <strong>Banned:</strong> {chat.ban_reason}
            </div>
        )}
        {!chat.is_active && (
            <div style={{ marginTop: '12px', color: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', padding: '8px', borderRadius: '8px' }}>
                <strong>Warning:</strong> Bot was kicked from this chat.
            </div>
        )}
      </div>

      <Section title="General Info" icon={Info}>
        {chat.username && <InfoRow label="Username" value={`@${chat.username}`} />}
        {chat.description && (
            <div style={{ padding: '8px 0', borderBottom: '1px solid var(--secondary-bg-color)' }}>
                <span style={{ color: 'var(--hint-color)', display: 'block', marginBottom: '4px' }}>Description</span>
                <span>{chat.description}</span>
            </div>
        )}
        {chat.invite_link && (
            <InfoRow label="Invite Link" value={
                <a href={chat.invite_link} target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', color: 'var(--link-color)' }}>
                    Link <ExternalLink size={14} style={{ marginLeft: '4px' }} />
                </a>
            } />
        )}
        <InfoRow label="Created At" value={new Date(chat.created_at).toLocaleString()} />
      </Section>

      <Section title="Settings" icon={Settings}>
        <InfoRow label="Language" value={chat.language_code} />
        <InfoRow label="Admins Only Add" value={chat.admins_only_add ? 'Yes' : 'No'} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0' }}>
          <span style={{ color: 'var(--hint-color)' }}>Trusted Chat</span>
          <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={chat.is_trusted}
              onChange={toggleTrust}
              style={{ width: '20px', height: '20px' }}
            />
          </label>
        </div>
      </Section>

      <Section title="Moderation" icon={Shield}>
        <InfoRow label="Warn Limit" value={chat.warn_limit} />
        <InfoRow label="Punishment" value={chat.warn_punishment} />
        <InfoRow label="Duration" value={`${chat.warn_duration} seconds`} />
      </Section>

      <Section title="Triggers" icon={Zap}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Manage chat triggers</span>
            <button
                onClick={() => navigate(`/chats/${id}/triggers`)}
                style={{
                    backgroundColor: 'var(--button-color)',
                    color: 'var(--button-text-color)',
                    padding: '8px 16px',
                    borderRadius: '8px',
                    border: 'none',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                }}
            >
                View Triggers
            </button>
        </div>
      </Section>

      <Section title="Actions" icon={AlertTriangle}>
        <div style={{ display: 'flex', gap: '12px' }}>
            <button
                onClick={banChat}
                style={{ flex: 1, backgroundColor: '#ef4444', color: 'white', padding: '12px', borderRadius: '8px', fontWeight: 'bold', border: 'none', cursor: 'pointer' }}
            >
                {chat.is_banned ? 'Update Ban' : 'Ban Chat'}
            </button>
            <button
                onClick={leaveChat}
                style={{ flex: 1, backgroundColor: 'var(--secondary-bg-color)', color: '#ef4444', padding: '12px', borderRadius: '8px', fontWeight: 'bold', border: 'none', cursor: 'pointer' }}
            >
                Leave Chat
            </button>
        </div>
      </Section>

      <Section title="Send Message" icon={MessageSquare}>
        <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--hint-color)', minHeight: '100px', backgroundColor: 'var(--bg-color)', color: 'var(--text-color)', marginBottom: '12px', resize: 'vertical' }}
            placeholder="Type a message to send to the chat..."
        />
        <button
            onClick={sendMessage}
            style={{ backgroundColor: 'var(--button-color)', color: 'var(--button-text-color)', padding: '12px', borderRadius: '8px', width: '100%', fontWeight: 'bold', border: 'none', cursor: 'pointer' }}
        >
            Send Message
        </button>
      </Section>
      {toastMessage && (
        <Toast
          message={toastMessage}
          onClose={() => setToastMessage(null)}
        />
      )}
    </div>
  );
};

export default ChatDetails;
