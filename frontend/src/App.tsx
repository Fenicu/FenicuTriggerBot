import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import UsersPage from './pages/Users';
import UserDetails from './pages/UserDetails';
import ChatsPage from './pages/Chats';
import ChatDetails from './pages/ChatDetails';
import ChatTriggers from './pages/ChatTriggers';

const App: React.FC = () => {
  return (
    <BrowserRouter basename="/webapp">
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="users/:id" element={<UserDetails />} />
          <Route path="chats" element={<ChatsPage />} />
          <Route path="chats/:id" element={<ChatDetails />} />
          <Route path="chats/:id/triggers" element={<ChatTriggers />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
