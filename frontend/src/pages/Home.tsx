import React from 'react';

const Home: React.FC = () => {
  return (
    <div style={{ padding: '16px' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>Admin Dashboard</h1>
      <div style={{ backgroundColor: 'var(--section-bg-color)', borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '18px', marginBottom: '8px' }}>Welcome</h2>
        <p style={{ color: 'var(--hint-color)' }}>
          Manage users and chats from this dashboard.
        </p>
      </div>
    </div>
  );
};

export default Home;
