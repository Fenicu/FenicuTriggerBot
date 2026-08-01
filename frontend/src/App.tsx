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
import { routeForStartParam } from './lib/startParam';

// Запасной путь для deep-link из кнопки модерации (?startapp=chat_<id>). Основной
// разбор идёт в main.tsx до монтирования роутера — здесь дочитываем параметр из
// window.Telegram на случай, когда Telegram переиспользовал уже открытый Mini App и
// hash с параметрами запуска до страницы не доехал. Срабатывает один раз за сессию,
// чтобы не перехватывать последующую навигацию пользователя.
const StartAppRedirect: React.FC = () => {
  const navigate = useNavigate();
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    // Уже на нужной карточке (hash переписан в main.tsx) — второй раз не навигируем
    if (window.location.hash.startsWith('#/chats/')) return;

    // start_param доступен только внутри Telegram Mini App — вне него объекта может не быть
    const route = routeForStartParam(window.Telegram?.WebApp?.initDataUnsafe?.start_param);
    if (route) {
      navigate(route);
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
