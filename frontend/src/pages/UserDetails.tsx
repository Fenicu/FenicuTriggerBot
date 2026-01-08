import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User } from '../types';
import { ArrowLeft } from 'lucide-react';

const UserDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

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

  const toggleRole = async (role: 'is_trusted' | 'is_bot_moderator') => {
    if (!user) return;
    try {
      const res = await apiClient.post<User>(`/users/${id}/role`, {
        [role]: !user[role],
      });
      setUser(res.data);
    } catch (error) {
      console.error(error);
      alert('Failed to update role');
    }
  };

  if (loading) return <div style={{ padding: '16px' }}>Loading...</div>;
  if (!user) return <div style={{ padding: '16px' }}>User not found</div>;

  return (
    <div style={{ padding: '16px' }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', color: 'var(--link-color)' }}>
        <ArrowLeft size={20} style={{ marginRight: '4px' }} /> Back
      </button>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 'bold' }}>{user.first_name} {user.last_name}</h1>
        <p style={{ color: 'var(--hint-color)' }}>@{user.username}</p>
        <p style={{ color: 'var(--hint-color)', fontSize: '12px', marginTop: '4px' }}>ID: {user.id}</p>
        <p style={{ color: 'var(--hint-color)', fontSize: '12px' }}>Created: {new Date(user.created_at).toLocaleDateString()}</p>
      </div>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--secondary-bg-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Trusted</span>
          <input
            type="checkbox"
            checked={user.is_trusted}
            onChange={() => toggleRole('is_trusted')}
            style={{ transform: 'scale(1.2)' }}
          />
        </div>
        <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Bot Moderator</span>
          <input
            type="checkbox"
            checked={user.is_bot_moderator}
            onChange={() => toggleRole('is_bot_moderator')}
            style={{ transform: 'scale(1.2)' }}
          />
        </div>
      </div>
    </div>
  );
};

export default UserDetails;
