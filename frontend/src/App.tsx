import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import ToastContainer from './components/Toast';
import ConfirmModal from './components/ConfirmModal';
import Home from './pages/Home';
import UsersPage from './pages/Users';
import UserDetails from './pages/UserDetails';
import ChatsPage from './pages/Chats';
import ChatDetails from './pages/ChatDetails';
import ChatTriggers from './pages/ChatTriggers';
import TriggersPage from './pages/Triggers';
import Login from './pages/Login';
import CaptchaPage from './pages/Captcha';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/captcha" element={<CaptchaPage />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="users/:id" element={<UserDetails />} />
            <Route path="chats" element={<ChatsPage />} />
            <Route path="chats/:id" element={<ChatDetails />} />
            <Route path="chats/:id/triggers" element={<ChatTriggers />} />
            <Route path="triggers" element={<TriggersPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <ToastContainer />
        <ConfirmModal />
      </HashRouter>
    </ErrorBoundary>
  );
};

export default App;
