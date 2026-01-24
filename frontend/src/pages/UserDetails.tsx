import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User, UserChat, PaginatedResponse } from '../types';
import { ArrowLeft, Info, Shield, MessageSquare, ShieldAlert, Bot } from 'lucide-react';
import Toast from '../components/Toast';
import Breadcrumbs from '../components/Breadcrumbs';
import UserAvatar from '../components/UserAvatar';

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

const UserDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [chats, setChats] = useState<UserChat[]>([]);
  const [chatsPage, setChatsPage] = useState(1);
  const [hasMoreChats, setHasMoreChats] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const res = await apiClient.get<User>(`/users/${id}`);
        setUser(res.data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, [id]);

  useEffect(() => {
    if (id) {
        fetchChats(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchChats = async (reset = false) => {
    if (!id) return;
    try {
        const currentPage = reset ? 1 : chatsPage;
        const res = await apiClient.get<PaginatedResponse<UserChat>>(`/users/${id}/chats`, {
            params: { page: currentPage, limit: 10 }
        });

        if (reset) {
            setChats(res.data.items);
        } else {
            setChats(prev => [...prev, ...res.data.items]);
        }

        setHasMoreChats(currentPage < res.data.pagination.total_pages);
        setChatsPage(currentPage + 1);
    } catch (error) {
        console.error('Failed to load user chats', error);
    }
  };

  const toggleRole = async (role: 'is_trusted' | 'is_bot_moderator') => {
    if (!user) return;
    try {
      const res = await apiClient.post<User>(`/users/${id}/role`, {
        [role]: !user[role],
      });
      setUser(res.data);
      setToastMessage(`Role ${role} updated`);
    } catch (error) {
      console.error(error);
      setToastMessage('Failed to update role');
    }
  };

  if (loading) return <div className="p-4">Loading...</div>;
  if (!user) return <div className="p-4">User not found</div>;

  return (
    <div className="p-4 max-w-200 mx-auto">
      <Breadcrumbs />
      <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur-md py-3 -mx-4 px-4 mb-4 border-b border-secondary-bg/50 shadow-sm md:hidden">
        <button onClick={() => navigate(-1)} className="flex items-center text-link bg-transparent border-none cursor-pointer text-base font-medium">
          <ArrowLeft size={20} className="mr-1" /> Back
        </button>
      </div>

      <div className="bg-section-bg rounded-xl p-5 mb-4 text-center">
        <div className="mx-auto mb-3 w-20 h-20">
            <UserAvatar userId={user.id} photoId={user.photo_id} className="w-20 h-20" />
        </div>
        <h1 className="text-2xl font-bold mb-2 flex items-center justify-center gap-2">
          {user.first_name} {user.last_name}
          {user.is_bot && <Bot size={24} className="text-hint" />}
        </h1>
        <div className="flex justify-center gap-2 flex-wrap">
            <span className="bg-secondary-bg px-2 py-1 rounded-md text-sm">
                @{user.username || 'No username'}
            </span>
            <span className="bg-secondary-bg px-2 py-1 rounded-md text-sm">
                ID: {user.id}
            </span>
        </div>
      </div>

      {user.is_gban && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-xl mb-4 flex items-center gap-3">
            <ShieldAlert size={24} />
            <div>
                <h3 className="font-bold m-0">Global Ban Active</h3>
                <p className="text-sm m-0 opacity-90">This user is globally banned.</p>
            </div>
        </div>
      )}

      <Section title="General Info" icon={Info}>
        <InfoRow label="Is Bot" value={user.is_bot ? 'Yes' : 'No'} />
        <InfoRow label="Language" value={user.language_code || 'Unknown'} />
        <InfoRow label="Premium" value={user.is_premium ? 'Yes' : 'No'} />
        <InfoRow label="Created At" value={new Date(user.created_at).toLocaleString()} />
      </Section>

      <Section title="Roles & Permissions" icon={Shield}>
        <div className="flex justify-between items-center py-2 border-b border-secondary-bg">
          <span className="text-hint">Trusted User</span>
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={user.is_trusted}
              onChange={() => toggleRole('is_trusted')}
              className="w-5 h-5"
            />
          </label>
        </div>
        <div className="flex justify-between items-center py-2">
          <span className="text-hint">Bot Moderator</span>
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={user.is_bot_moderator}
              onChange={() => toggleRole('is_bot_moderator')}
              className="w-5 h-5"
            />
          </label>
        </div>
      </Section>

      <Section title="Chats" icon={MessageSquare}>
        {chats.length === 0 ? (
            <div className="text-hint text-center p-4">
                No chats found
            </div>
        ) : (
            <div className="flex flex-col gap-2">
                {chats.map((userChat) => (
                    <div
                        key={userChat.chat.id}
                        onClick={() => navigate(`/chats/${userChat.chat.id}`)}
                        className="p-3 bg-bg rounded-lg cursor-pointer flex justify-between items-center"
                    >
                        <div>
                            <div className="font-bold">{userChat.chat.title || userChat.chat.username || `Chat ${userChat.chat.id}`}</div>
                            <div className="text-xs text-hint">ID: {userChat.chat.id}</div>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${userChat.is_active ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                                {userChat.is_active ? 'Active' : 'Inactive'}
                            </span>
                            {userChat.is_admin && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500">
                                    Admin
                                </span>
                            )}
                        </div>
                    </div>
                ))}
                {hasMoreChats && (
                    <button
                        onClick={() => fetchChats(false)}
                        className="w-full p-2 mt-2 text-link bg-transparent border-none cursor-pointer"
                    >
                        Load More
                    </button>
                )}
            </div>
        )}
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

export default UserDetails;
