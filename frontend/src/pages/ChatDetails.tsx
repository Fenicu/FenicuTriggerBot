import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient, { chatsApi } from '../api/client';
import { toast, confirm } from '../store/store';
import ChatSettingsForm from '../components/ChatSettingsForm';
import type { Chat, ChatUser } from '../types';
import { ArrowLeft, ExternalLink, Shield, AlertTriangle, MessageSquare, Info, Zap, Users, Bot } from 'lucide-react';
import Breadcrumbs from '../components/Breadcrumbs';
import ChatAvatar from '../components/ChatAvatar';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';

const InfoRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="flex justify-between py-2.5 border-b border-border last:border-b-0">
    <span className="text-hint">{label}</span>
    <span className="font-medium text-right">{value}</span>
  </div>
);

const ChatDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [chat, setChat] = useState<Chat | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [users, setUsers] = useState<ChatUser[]>([]);
  const [usersPage, setUsersPage] = useState(1);
  const [hasMoreUsers, setHasMoreUsers] = useState(true);

  useEffect(() => {
    const fetchChat = async () => {
      if (!id) return;
      try {
        const chatData = await chatsApi.getById(parseInt(id));
        setChat(chatData);
      } catch {
        // Error handled by interceptor
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
  }, [id]);

  const fetchUsers = async (reset = false) => {
    if (!id) return;
    try {
      const currentPage = reset ? 1 : usersPage;
      const res = await chatsApi.getUsers(parseInt(id), { page: currentPage, limit: 10 });

      if (reset) {
        setUsers(res.items);
      } else {
        setUsers(prev => [...prev, ...res.items]);
      }

      setHasMoreUsers(currentPage < res.pagination.total_pages);
      setUsersPage(currentPage + 1);
    } catch {
      // Error handled by interceptor
    }
  };

  const banChat = async () => {
    if (!id) return;

    const reason = prompt('Enter ban reason:');
    if (!reason) return;

    try {
      await chatsApi.ban(parseInt(id), { reason });
      const chatData = await chatsApi.getById(parseInt(id));
      setChat(chatData);
      toast.success('Chat banned');
    } catch {
      // Error handled by interceptor
    }
  };

  const leaveChat = async () => {
    if (!id) return;

    const confirmed = await confirm({
      title: 'Leave Chat',
      message: 'Are you sure you want the bot to leave this chat?',
      confirmText: 'Leave',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await apiClient.post(`/chats/${id}/leave`);
      toast.success('Bot left the chat');
      navigate('/chats');
    } catch {
      // Error handled by interceptor
    }
  };

  const sendMessage = async () => {
    if (!message.trim() || !id) return;
    try {
      await apiClient.post(`/chats/${id}/message`, { text: message });
      setMessage('');
      toast.success('Message sent');
    } catch {
      // Error handled by interceptor
    }
  };

  if (loading) return <div className="p-4">Loading...</div>;
  if (!chat) return <div className="p-4">Chat not found</div>;

  return (
    <div className="p-4 max-w-200 mx-auto">
      <Breadcrumbs />
      <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur-md py-3 -mx-4 px-4 mb-4 border-b border-border shadow-sm md:hidden">
        <button onClick={() => navigate(-1)} className="flex items-center text-link bg-transparent border-none cursor-pointer text-base font-medium">
          <ArrowLeft size={20} className="mr-1" /> Back
        </button>
      </div>

      <div className="bg-surface border border-border rounded-xl p-5 mb-4 text-center">
        <div className="mx-auto mb-3 w-20 h-20">
          <ChatAvatar chatId={chat.id} photoId={chat.photo_id} className="w-20 h-20" />
        </div>
        <h1 className="text-2xl font-bold mb-2">
          {chat.title || chat.username || `Chat ${chat.id}`}
        </h1>
        <div className="flex justify-center gap-2 flex-wrap">
          {chat.type && (
            <span className="bg-elevated px-2 py-1 rounded-md text-sm capitalize">
              {chat.type}
            </span>
          )}
          <span className="bg-elevated px-2 py-1 rounded-md text-sm">
            ID: {chat.id}
          </span>
          {chat.is_trusted && <Badge variant="green">Trusted</Badge>}
        </div>

        <button
          onClick={() => navigate(`/chats/${id}/triggers`)}
          className={`mt-4 px-5 py-2.5 rounded-lg border-none cursor-pointer font-bold inline-flex items-center gap-2 text-sm ${
            chat.triggers_count > 0 ? 'bg-button text-button-text' : 'bg-elevated text-hint'
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

      <Card icon={Info} iconGradient="bg-gradient-to-br from-blue-500 to-cyan-500" title="General Info">
        {chat.username && <InfoRow label="Username" value={`@${chat.username}`} />}
        {chat.description && (
          <div className="py-2.5 border-b border-border">
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
        <InfoRow label="Created At" value={new Date(chat.created_at).toLocaleString(navigator.language)} />
      </Card>

      <ChatSettingsForm chatId={parseInt(id!)} isBotAdmin />

      <Card icon={Shield} iconGradient="bg-gradient-to-br from-violet-500 to-purple-500" title="Moderation">
        <InfoRow label="Warn Limit" value={chat.warn_limit} />
        <InfoRow label="Punishment" value={chat.warn_punishment} />
        <InfoRow label="Duration" value={`${chat.warn_duration} seconds`} />
      </Card>

      <Card icon={AlertTriangle} iconGradient="bg-gradient-to-br from-orange-500 to-red-500" title="Actions">
        <div className="flex gap-3">
          <button
            onClick={banChat}
            className="flex-1 bg-red-500 text-white p-3 rounded-lg font-bold border-none cursor-pointer"
          >
            {chat.is_banned ? 'Update Ban' : 'Ban Chat'}
          </button>
          <button
            onClick={leaveChat}
            className="flex-1 bg-elevated text-[#f87171] p-3 rounded-lg font-bold border-none cursor-pointer"
          >
            Leave Chat
          </button>
        </div>
      </Card>

      <Card icon={Users} iconGradient="bg-gradient-to-br from-green-500 to-teal-500" title="Users">
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
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/users/${chatUser.user.id}`); } }}
                role="button"
                tabIndex={0}
                className="p-3 bg-elevated rounded-[10px] cursor-pointer flex justify-between items-center"
              >
                <div>
                  <div className="font-bold flex items-center gap-1">
                    {chatUser.user.first_name} {chatUser.user.last_name}
                    {chatUser.user.is_bot && <Bot size={14} className="text-hint" />}
                  </div>
                  <div className="text-xs text-hint">@{chatUser.user.username || 'No username'}</div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant={chatUser.is_active ? 'green' : 'red'}>
                    {chatUser.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                  {chatUser.is_admin && (
                    <Badge variant="blue">Admin</Badge>
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
      </Card>

      <Card icon={MessageSquare} iconGradient="bg-gradient-to-br from-sky-500 to-blue-500" title="Send Message">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full p-3 rounded-lg border border-border min-h-25 bg-bg text-text mb-3 resize-y"
          placeholder="Type a message to send to the chat..."
        />
        <button
          onClick={sendMessage}
          className="bg-button text-button-text p-3 rounded-lg w-full font-bold border-none cursor-pointer"
        >
          Send Message
        </button>
      </Card>
    </div>
  );
};

export default ChatDetails;
