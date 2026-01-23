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
    <div className="flex h-screen overflow-hidden bg-bg text-text">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex flex-col w-64 bg-secondary-bg border-r border-black/10">
        <div className="p-6 border-b border-black/10">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Zap className="text-button" size={24} />
            <span>Trigger App</span>
          </h1>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          {tabs.map((tab) => {
            const isActive = location.pathname === tab.path;
            return (
              <button
                key={tab.path}
                onClick={() => navigate(tab.path)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-button text-button-text'
                    : 'text-text hover:bg-white/5'
                }`}
              >
                <tab.icon size={20} />
                <span className="font-medium">{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
          <div className="max-w-7xl mx-auto w-full">
            <Outlet />
          </div>
        </main>

        {/* Mobile Bottom Navigation */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 bg-secondary-bg border-t border-black/10 flex justify-around py-2 z-50 safe-area-bottom">
          {tabs.map((tab) => {
            const isActive = location.pathname === tab.path;
            return (
              <button
                key={tab.path}
                onClick={() => navigate(tab.path)}
                className={`flex flex-col items-center bg-transparent w-full py-1 ${
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
    </div>
  );
};

export default Layout;
