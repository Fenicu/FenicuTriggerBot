import React, { useEffect, useRef } from 'react';
import { HashRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
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
import ChatSettings from './pages/ChatSettings';

// start_param вида chat_<id> (в т.ч. отрицательные id супергрупп/каналов)
const START_PARAM_CHAT_RE = /^chat_(-?\d+)$/;

// Обрабатывает deep-link из кнопки модерации (?startapp=chat_<id>): при запуске
// Mini App сразу переводит на карточку нужного чата. Срабатывает ровно один раз
// за сессию приложения, чтобы не перехватывать последующую навигацию пользователя.
const StartAppRedirect: React.FC = () => {
  const navigate = useNavigate();
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    // start_param доступен только внутри Telegram Mini App — вне него объекта может не быть
    const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param;
    if (!startParam) return;

    const match = START_PARAM_CHAT_RE.exec(startParam);
    if (match) {
      navigate(`/chats/${match[1]}`);
    }
  }, [navigate]);

  return null;
};

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <HashRouter>
        <StartAppRedirect />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/captcha" element={<CaptchaPage />} />
          <Route path="/settings/:chatId" element={<ChatSettings />} />
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
