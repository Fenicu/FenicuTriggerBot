import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat, ChatUser, PaginatedResponse } from '../types';
import { ArrowLeft, ExternalLink, Shield, AlertTriangle, MessageSquare, Info, Settings, Zap, Users } from 'lucide-react';
import Toast from '../components/Toast';

const InfoRow = ({ label, value }: { label: string, value: React.ReactNode }) => (
  <div className="flex justify-between py-2 border-b border-secondary-bg">
    <span className="text-hint">{label}</span>
    <span className="font-medium text-right">{value}</span>
  </div>
);

const Section = ({ title, icon: Icon, children }: { title: string, icon: React.ElementType, children: React.ReactNode }) => (
  <div className="bg-section-bg rounded-xl p-4 mb-4">
    <div className="flex items-center mb-3 text-link">
      <Icon size={20} className="mr-2" />
      <h2 className="text-base font-bold m-0">{title}</h2>
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
  const [users, setUsers] = useState<ChatUser[]>([]);
  const [usersPage, setUsersPage] = useState(1);
  const [hasMoreUsers, setHasMoreUsers] = useState(true);

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
    if (id) {
        fetchUsers(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchUsers = async (reset = false) => {
    if (!id) return;
    try {
        const currentPage = reset ? 1 : usersPage;
        const res = await apiClient.get<PaginatedResponse<ChatUser>>(`/chats/${id}/users`, {
            params: { page: currentPage, limit: 10 }
        });

        if (reset) {
            setUsers(res.data.items);
        } else {
            setUsers(prev => [...prev, ...res.data.items]);
        }

        setHasMoreUsers(currentPage < res.data.pagination.total_pages);
        setUsersPage(currentPage + 1);
    } catch (error) {
        console.error('Failed to load chat users', error);
    }
  };

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

  if (loading) return <div className="p-4">Loading...</div>;
  if (!chat) return <div className="p-4">Chat not found</div>;

  return (
    <div className="p-4 max-w-200 mx-auto">
      <button onClick={() => navigate(-1)} className="mb-4 flex items-center text-link bg-transparent border-none cursor-pointer text-base">
        <ArrowLeft size={20} className="mr-1" /> Back
      </button>

      <div className="bg-section-bg rounded-xl p-5 mb-4 text-center">
        {avatarUrl && (
          <img
            src={avatarUrl}
            alt="Chat Avatar"
            className="w-20 h-20 rounded-full object-cover mb-3 mx-auto"
          />
        )}
        <h1 className="text-2xl font-bold mb-2">
          {chat.title || chat.username || `Chat ${chat.id}`}
        </h1>
        <div className="flex justify-center gap-2 flex-wrap">
            {chat.type && (
                <span className="bg-secondary-bg px-2 py-1 rounded-md text-sm capitalize">
                    {chat.type}
                </span>
            )}
            <span className="bg-secondary-bg px-2 py-1 rounded-md text-sm">
                ID: {chat.id}
            </span>
        </div>

        <button
            onClick={() => navigate(`/chats/${id}/triggers`)}
            className={`mt-4 px-5 py-2.5 rounded-lg border-none cursor-pointer font-bold inline-flex items-center gap-2 text-sm ${
                chat.triggers_count > 0 ? 'bg-button text-button-text' : 'bg-secondary-bg text-hint'
            }`}
        >
            <Zap size={18} />
            View Triggers ({chat.triggers_count})
        </button>

        {chat.is_banned && (
            <div className="mt-3 text-red-500 bg-red-500/10 p-2 rounded-lg">
                <strong>Banned:</strong> {chat.ban_reason}
            </div>
        )}
        {!chat.is_active && (
            <div className="mt-3 text-amber-500 bg-amber-500/10 p-2 rounded-lg">
                <strong>Warning:</strong> Bot was kicked from this chat.
            </div>
        )}
      </div>

      <Section title="General Info" icon={Info}>
        {chat.username && <InfoRow label="Username" value={`@${chat.username}`} />}
        {chat.description && (
            <div className="py-2 border-b border-secondary-bg">
                <span className="text-hint block mb-1">Description</span>
                <span>{chat.description}</span>
            </div>
        )}
        {chat.invite_link && (
            <InfoRow label="Invite Link" value={
                <a href={chat.invite_link} target="_blank" rel="noopener noreferrer" className="flex items-center text-link">
                    Link <ExternalLink size={14} className="ml-1" />
                </a>
            } />
        )}
        <InfoRow label="Created At" value={new Date(chat.created_at).toLocaleString()} />
      </Section>

      <Section title="Settings" icon={Settings}>
        <InfoRow label="Language" value={chat.language_code} />
        <InfoRow label="Admins Only Add" value={chat.admins_only_add ? 'Yes' : 'No'} />
        <div className="flex justify-between items-center py-2">
          <span className="text-hint">Trusted Chat</span>
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={chat.is_trusted}
              onChange={toggleTrust}
              className="w-5 h-5"
            />
          </label>
        </div>
      </Section>

      <Section title="Moderation" icon={Shield}>
        <InfoRow label="Warn Limit" value={chat.warn_limit} />
        <InfoRow label="Punishment" value={chat.warn_punishment} />
        <InfoRow label="Duration" value={`${chat.warn_duration} seconds`} />
      </Section>

      <Section title="Actions" icon={AlertTriangle}>
        <div className="flex gap-3">
            <button
                onClick={banChat}
                className="flex-1 bg-red-500 text-white p-3 rounded-lg font-bold border-none cursor-pointer"
            >
                {chat.is_banned ? 'Update Ban' : 'Ban Chat'}
            </button>
            <button
                onClick={leaveChat}
                className="flex-1 bg-secondary-bg text-red-500 p-3 rounded-lg font-bold border-none cursor-pointer"
            >
                Leave Chat
            </button>
        </div>
      </Section>

      <Section title="Users" icon={Users}>
        {users.length === 0 ? (
            <div className="text-hint text-center p-4">
                No users found
            </div>
        ) : (
            <div className="flex flex-col gap-2">
                {users.map((chatUser) => (
                    <div
                        key={chatUser.user.id}
                        onClick={() => navigate(`/users/${chatUser.user.id}`)}
                        className="p-3 bg-bg rounded-lg cursor-pointer flex justify-between items-center"
                    >
                        <div>
                            <div className="font-bold">{chatUser.user.first_name} {chatUser.user.last_name}</div>
                            <div className="text-xs text-hint">@{chatUser.user.username || 'No username'}</div>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${chatUser.is_active ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                                {chatUser.is_active ? 'Active' : 'Inactive'}
                            </span>
                            {chatUser.is_admin && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500">
                                    Admin
                                </span>
                            )}
                        </div>
                    </div>
                ))}
                {hasMoreUsers && (
                    <button
                        onClick={() => fetchUsers(false)}
                        className="w-full p-2 mt-2 text-link bg-transparent border-none cursor-pointer"
                    >
                        Load More
                    </button>
                )}
            </div>
        )}
      </Section>

      <Section title="Send Message" icon={MessageSquare}>
        <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="w-full p-3 rounded-lg border border-hint min-h-25 bg-bg text-text mb-3 resize-y"
            placeholder="Type a message to send to the chat..."
        />
        <button
            onClick={sendMessage}
            className="bg-button text-button-text p-3 rounded-lg w-full font-bold border-none cursor-pointer"
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
