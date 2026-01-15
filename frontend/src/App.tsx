import React, { Suspense } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import UsersPage from './pages/Users';
import UserDetails from './pages/UserDetails';
import ChatsPage from './pages/Chats';
import ChatDetails from './pages/ChatDetails';
import ChatTriggers from './pages/ChatTriggers';
import Login from './pages/Login';
import CaptchaPage from './pages/Captcha';

const Home = React.lazy(() => import('./pages/Home'));

const App: React.FC = () => {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/captcha" element={<CaptchaPage />} />
        <Route path="/" element={<Layout />}>
          <Route index element={
            <Suspense fallback={<div className="p-4 text-center">Loading Home...</div>}>
              <Home />
            </Suspense>
          } />
          <Route path="users" element={<UsersPage />} />
          <Route path="users/:id" element={<UserDetails />} />
          <Route path="chats" element={<ChatsPage />} />
          <Route path="chats/:id" element={<ChatDetails />} />
          <Route path="chats/:id/triggers" element={<ChatTriggers />} />
        </Route>
      </Routes>
    </HashRouter>
  );
};

export default App;
