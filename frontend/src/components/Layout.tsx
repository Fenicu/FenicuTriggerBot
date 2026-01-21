import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Users, MessageSquare, Home, Zap } from 'lucide-react';

const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const tabs = [
    { path: '/', icon: Home, label: 'Home' },
    { path: '/users', icon: Users, label: 'Users' },
    { path: '/chats', icon: MessageSquare, label: 'Chats' },
    { path: '/triggers', icon: Zap, label: 'Triggers' },
  ];

  return (
    <div className="flex flex-col min-h-screen">
      <div className="flex-1 overflow-y-auto pb-15">
        <Outlet />
      </div>
      <div className="fixed bottom-0 left-0 right-0 bg-secondary-bg border-t border-black/10 flex justify-around py-2 z-50">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path;
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              className={`flex flex-col items-center bg-transparent ${
                isActive ? 'text-button' : 'text-hint'
              }`}
            >
              <tab.icon size={24} />
              <span className="text-[10px] mt-1">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default Layout;
