import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Users, MessageSquare, Home } from 'lucide-react';

const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const tabs = [
    { path: '/', icon: Home, label: 'Home' },
    { path: '/users', icon: Users, label: 'Users' },
    { path: '/chats', icon: MessageSquare, label: 'Chats' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '60px' }}>
        <Outlet />
      </div>
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: 'var(--secondary-bg-color)',
        borderTop: '1px solid rgba(0,0,0,0.1)',
        display: 'flex',
        justifyContent: 'space-around',
        padding: '8px 0',
        zIndex: 1000
      }}>
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path;
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                color: isActive ? 'var(--button-color)' : 'var(--hint-color)',
                background: 'transparent'
              }}
            >
              <tab.icon size={24} />
              <span style={{ fontSize: '10px', marginTop: '4px' }}>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default Layout;
