import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User } from '../types';
import { ArrowLeft, Info, Shield, User as UserIcon } from 'lucide-react';
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

const UserDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);

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
    if (user?.photo_id) {
      apiClient.get(`/users/${user.id}/photo`, { responseType: 'blob' })
        .then(res => {
          const url = URL.createObjectURL(res.data);
          setAvatarUrl(url);
        })
        .catch(err => console.error('Failed to load avatar', err));
    } else {
      setAvatarUrl(null);
    }
  }, [user]);

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

  if (loading) return <div style={{ padding: '16px' }}>Loading...</div>;
  if (!user) return <div style={{ padding: '16px' }}>User not found</div>;

  return (
    <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', color: 'var(--link-color)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}>
        <ArrowLeft size={20} style={{ marginRight: '4px' }} /> Back
      </button>

      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '20px', marginBottom: '16px', textAlign: 'center' }}>
        <div style={{
            width: '80px',
            height: '80px',
            borderRadius: '50%',
            backgroundColor: 'var(--secondary-bg-color)',
            margin: '0 auto 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--hint-color)',
            overflow: 'hidden'
        }}>
            {avatarUrl ? (
                <img src={avatarUrl} alt="User Avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
                <UserIcon size={40} />
            )}
        </div>
        <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>
          {user.first_name} {user.last_name}
        </h1>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ backgroundColor: 'var(--secondary-bg-color)', padding: '4px 8px', borderRadius: '6px', fontSize: '14px' }}>
                @{user.username || 'No username'}
            </span>
            <span style={{ backgroundColor: 'var(--secondary-bg-color)', padding: '4px 8px', borderRadius: '6px', fontSize: '14px' }}>
                ID: {user.id}
            </span>
        </div>
      </div>

      <Section title="General Info" icon={Info}>
        <InfoRow label="Language" value={user.language_code || 'Unknown'} />
        <InfoRow label="Premium" value={user.is_premium ? 'Yes' : 'No'} />
        <InfoRow label="Created At" value={new Date(user.created_at).toLocaleString()} />
      </Section>

      <Section title="Roles & Permissions" icon={Shield}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--secondary-bg-color)' }}>
          <span style={{ color: 'var(--hint-color)' }}>Trusted User</span>
          <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={user.is_trusted}
              onChange={() => toggleRole('is_trusted')}
              style={{ width: '20px', height: '20px' }}
            />
          </label>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0' }}>
          <span style={{ color: 'var(--hint-color)' }}>Bot Moderator</span>
          <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={user.is_bot_moderator}
              onChange={() => toggleRole('is_bot_moderator')}
              style={{ width: '20px', height: '20px' }}
            />
          </label>
        </div>
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
