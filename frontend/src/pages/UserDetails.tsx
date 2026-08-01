import React, { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { usersApi, triggersApi } from '../api/client';
import { toast, confirm } from '../store/store';
import type { User, UserChat, PaginatedResponse, Trigger, TriggerAuthorChat } from '../types';
import { ArrowLeft, Info, Shield, MessageSquare, ShieldAlert, Bot, Trash2, Zap, ChevronDown, ChevronRight } from 'lucide-react';
import Breadcrumbs from '../components/Breadcrumbs';
import UserAvatar from '../components/UserAvatar';
import apiClient from '../api/client';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import Toggle from '../components/ui/Toggle';
import Skeleton from '../components/Skeleton';
import StatusBadge from '../components/StatusBadge';
import { formatDate, formatDateTime } from '../lib/dateFormat';

const InfoRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="flex justify-between py-2.5 border-b border-border last:border-b-0">
    <span className="text-hint">{label}</span>
    <span className="font-medium text-right">{value}</span>
  </div>
);

const UserDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [chats, setChats] = useState<UserChat[]>([]);
  const [chatsPage, setChatsPage] = useState(1);
  const [hasMoreChats, setHasMoreChats] = useState(true);
  // Счётчик запросов чатов: fetchChats дёргается и из эффекта, и из кнопки
  // "Load More" вне эффекта, поэтому cancelled-флаг не подходит — нужен id запроса
  const chatsRequestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const fetchUser = async () => {
      if (!id) return;
      try {
        const userData = await usersApi.getById(parseInt(id));
        if (!cancelled) setUser(userData);
      } catch {
        // Error handled by interceptor
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchUser();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const fetchChats = async (reset = false) => {
    if (!id) return;
    const requestId = ++chatsRequestIdRef.current;
    try {
      const currentPage = reset ? 1 : chatsPage;
      const res = await apiClient.get<PaginatedResponse<UserChat>>(`/users/${id}/chats`, {
        params: { page: currentPage, limit: 10 }
      });

      // Ответ устарел (ушёл новый запрос — смена id или повторный клик) — игнорируем
      if (requestId !== chatsRequestIdRef.current) return;

      if (reset) {
        setChats(res.data.items);
      } else {
        setChats(prev => [...prev, ...res.data.items]);
      }

      setHasMoreChats(currentPage < res.data.pagination.total_pages);
      setChatsPage(currentPage + 1);
    } catch {
      // Error handled by interceptor
    }
  };

  useEffect(() => {
    if (id) {
      // fetchChats — обычный fetch-эффект: setState внутри неё выполняется только
      // после await сетевого запроса, а не синхронно; линтер не умеет заглянуть
      // в тело функции, объявленной вне эффекта, и подстраховывается
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchChats(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // ---- Триггеры пользователя: чаты, где он их создавал ----
  const [authorChats, setAuthorChats] = useState<TriggerAuthorChat[]>([]);
  const [authorChatsLoading, setAuthorChatsLoading] = useState(true);
  const [authorChatsError, setAuthorChatsError] = useState(false);
  const authorChatsRequestIdRef = useRef(0);

  // Аккордеон: раскрытый чат и подгруженные для него триггеры автора
  const [expandedChatId, setExpandedChatId] = useState<number | null>(null);
  const [chatTriggerItems, setChatTriggerItems] = useState<Record<number, Trigger[]>>({});
  const [chatTriggerTotal, setChatTriggerTotal] = useState<Record<number, number>>({});
  const [chatTriggerPage, setChatTriggerPage] = useState<Record<number, number>>({});
  const [chatTriggerLoading, setChatTriggerLoading] = useState<Record<number, boolean>>({});
  // Счётчик запросов на чат — раскрытие/закрытие/"Показать ещё" может обогнать предыдущий ответ
  const chatTriggerRequestIdRef = useRef<Record<number, number>>({});

  const fetchAuthorChats = async () => {
    if (!id) return;
    const requestId = ++authorChatsRequestIdRef.current;
    setAuthorChatsLoading(true);
    setAuthorChatsError(false);
    try {
      const res = await triggersApi.getAuthorChats(parseInt(id));
      if (authorChatsRequestIdRef.current !== requestId) return;
      setAuthorChats(res.items);
    } catch {
      if (authorChatsRequestIdRef.current !== requestId) return;
      setAuthorChatsError(true);
    } finally {
      if (authorChatsRequestIdRef.current === requestId) {
        setAuthorChatsLoading(false);
      }
    }
  };

  useEffect(() => {
    if (id) {
      // fetchAuthorChats — обычный fetch-эффект, см. комментарий у fetchChats выше
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchAuthorChats();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchChatTriggers = async (chatId: number, reset: boolean) => {
    if (!id) return;
    const requestId = (chatTriggerRequestIdRef.current[chatId] ?? 0) + 1;
    chatTriggerRequestIdRef.current[chatId] = requestId;
    setChatTriggerLoading((prev) => ({ ...prev, [chatId]: true }));
    try {
      const currentPage = reset ? 1 : (chatTriggerPage[chatId] ?? 1);
      const res = await triggersApi.getAll({
        created_by: parseInt(id),
        chat_id: chatId,
        page: currentPage,
        limit: 20,
      });

      // Игнорируем устаревший ответ, если за время запроса ушёл более новый
      if (chatTriggerRequestIdRef.current[chatId] !== requestId) return;

      setChatTriggerItems((prev) => ({
        ...prev,
        [chatId]: reset ? res.items : [...(prev[chatId] ?? []), ...res.items],
      }));
      setChatTriggerTotal((prev) => ({ ...prev, [chatId]: res.total }));
      setChatTriggerPage((prev) => ({ ...prev, [chatId]: currentPage + 1 }));
    } catch {
      // Error handled by interceptor
    } finally {
      if (chatTriggerRequestIdRef.current[chatId] === requestId) {
        setChatTriggerLoading((prev) => ({ ...prev, [chatId]: false }));
      }
    }
  };

  const toggleChatExpand = (chatId: number) => {
    if (expandedChatId === chatId) {
      setExpandedChatId(null);
      return;
    }
    setExpandedChatId(chatId);
    if (!chatTriggerItems[chatId]) {
      fetchChatTriggers(chatId, true);
    }
  };

  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!id) return;
    const confirmed = await confirm({
      title: 'Удалить пользователя',
      message: `Это навсегда удалит пользователя ${user?.first_name || user?.username || id} и все связанные данные: сессии капчи, предупреждения, историю доверия и участие в чатах. Триггеры, созданные этим пользователем, будут сохранены. Действие необратимо.`,
      confirmText: 'Удалить',
      cancelText: 'Отмена',
      variant: 'danger',
    });
    if (!confirmed) return;
    setDeleting(true);
    try {
      await usersApi.delete(parseInt(id));
      toast.success('Пользователь удалён');
      navigate('/users');
    } catch {
      // Error handled by interceptor
    } finally {
      setDeleting(false);
    }
  };

  const toggleRole = async (role: 'is_trusted' | 'is_bot_moderator') => {
    if (!user || !id) return;
    try {
      const updatedUser = await usersApi.updateRole(parseInt(id), {
        [role]: !user[role],
      });
      setUser(updatedUser);
      toast.success(`Роль обновлена`);
    } catch {
      // Error handled by interceptor
    }
  };

  if (loading) return <div className="p-4">Загрузка…</div>;
  if (!user) return <div className="p-4">Пользователь не найден</div>;

  return (
    <div className="p-4 max-w-200 mx-auto">
      <Breadcrumbs />
      <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur-md py-3 -mx-4 px-4 mb-4 border-b border-border shadow-sm md:hidden">
        <button onClick={() => navigate(-1)} className="flex items-center text-link bg-transparent border-none cursor-pointer text-base font-medium">
          <ArrowLeft size={20} className="mr-1" /> Назад
        </button>
      </div>

      <div className="bg-surface border border-border rounded-xl p-5 mb-4 text-center">
        <div className="mx-auto mb-3 w-20 h-20">
          <UserAvatar userId={user.id} photoId={user.photo_id} className="w-20 h-20" />
        </div>
        <h1 className="text-2xl font-bold mb-2 flex items-center justify-center gap-2">
          {user.first_name} {user.last_name}
          {user.is_bot && <Bot size={24} className="text-hint" />}
        </h1>
        <div className="flex justify-center gap-2 flex-wrap">
          <span className="bg-elevated px-2 py-1 rounded-md text-sm">
            @{user.username || 'Без username'}
          </span>
          <span className="bg-elevated px-2 py-1 rounded-md text-sm">
            ID: {user.id}
          </span>
        </div>
      </div>

      {user.is_gban && (
        <div className="bg-danger-soft border border-danger/20 text-danger p-4 rounded-xl mb-4 flex items-center gap-3">
          <ShieldAlert size={24} />
          <div>
            <h3 className="font-bold m-0">Глобальный бан активен</h3>
            <p className="text-sm m-0 opacity-90">Этот пользователь заблокирован глобально.</p>
          </div>
        </div>
      )}

      <Card icon={Info} title="Общие сведения">
        <InfoRow label="Бот" value={user.is_bot ? 'Да' : 'Нет'} />
        <InfoRow label="Язык" value={user.language_code || 'Неизвестно'} />
        <InfoRow label="Premium" value={user.is_premium ? 'Да' : 'Нет'} />
        <InfoRow label="Создан" value={formatDateTime(user.created_at)} />
      </Card>

      <Card icon={Shield} title="Роли и права">
        <div className="flex justify-between items-center py-2.5 border-b border-border">
          <span className="text-hint">Доверенный</span>
          <Toggle value={user.is_trusted} onChange={() => toggleRole('is_trusted')} />
        </div>
        <div className="flex justify-between items-center py-2.5">
          <span className="text-hint">Модератор бота</span>
          <Toggle value={user.is_bot_moderator} onChange={() => toggleRole('is_bot_moderator')} />
        </div>
      </Card>

      <Card icon={MessageSquare} title="Чаты">
        {chats.length === 0 ? (
          <div className="text-hint text-center p-4">
            Чатов пока нет
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {chats.map((userChat) => (
              <div
                key={userChat.chat.id}
                onClick={() => navigate(`/chats/${userChat.chat.id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/chats/${userChat.chat.id}`); } }}
                role="button"
                tabIndex={0}
                className="p-3 bg-elevated rounded-[10px] cursor-pointer flex justify-between items-center"
              >
                <div>
                  <div className="font-bold">{userChat.chat.title || userChat.chat.username || `Чат ${userChat.chat.id}`}</div>
                  <div className="text-xs text-hint">ID: {userChat.chat.id}</div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant={userChat.is_active ? 'green' : 'red'}>
                    {userChat.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                  {userChat.is_admin && (
                    <Badge variant="blue">Админ</Badge>
                  )}
                </div>
              </div>
            ))}
            {hasMoreChats && (
              <button
                onClick={() => fetchChats(false)}
                className="w-full p-2 mt-2 text-link bg-transparent border-none cursor-pointer"
              >
                Показать ещё
              </button>
            )}
          </div>
        )}
      </Card>

      <Card icon={Zap} title="Триггеры">
        {authorChatsLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="w-full h-14 rounded-[10px]" />
            ))}
          </div>
        ) : authorChatsError ? (
          <div className="bg-danger-soft text-danger p-3 rounded-lg text-sm">
            Не удалось загрузить чаты с триггерами
          </div>
        ) : authorChats.length === 0 ? (
          <div className="text-hint text-center p-4">
            Пользователь ещё не создавал триггеров
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {authorChats.map((entry) => {
              const isExpanded = expandedChatId === entry.chat_id;
              const triggers = chatTriggerItems[entry.chat_id] ?? [];
              const loadingTriggers = chatTriggerLoading[entry.chat_id] ?? false;
              const hasMoreTriggers = triggers.length < (chatTriggerTotal[entry.chat_id] ?? 0);

              return (
                <div key={entry.chat_id} className="bg-elevated rounded-[10px] overflow-hidden">
                  <div
                    onClick={() => toggleChatExpand(entry.chat_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleChatExpand(entry.chat_id); } }}
                    role="button"
                    tabIndex={0}
                    className="p-3 flex items-center gap-2 cursor-pointer min-w-0"
                  >
                    {isExpanded ? (
                      <ChevronDown size={16} className="text-hint shrink-0" />
                    ) : (
                      <ChevronRight size={16} className="text-hint shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <span
                        role="link"
                        tabIndex={0}
                        onClick={(e) => { e.stopPropagation(); navigate(`/chats/${entry.chat_id}`); }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.stopPropagation();
                            e.preventDefault();
                            navigate(`/chats/${entry.chat_id}`);
                          }
                        }}
                        className="font-bold truncate block hover:text-link transition-colors"
                      >
                        {entry.chat_title || `Чат ${entry.chat_id}`}
                      </span>
                      <div className="text-xs text-hint truncate">
                        Триггеров: {entry.trigger_count} · Последний: {formatDate(entry.last_created_at)}
                      </div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-border p-2 flex flex-col gap-1.5">
                      {loadingTriggers && triggers.length === 0 ? (
                        <div className="flex flex-col gap-1.5 p-1">
                          {Array.from({ length: 2 }).map((_, i) => (
                            <Skeleton key={i} className="w-full h-10 rounded-lg" />
                          ))}
                        </div>
                      ) : triggers.length === 0 ? (
                        <div className="text-hint text-sm text-center p-2">
                          Нет триггеров
                        </div>
                      ) : (
                        <>
                          {triggers.map((trigger) => (
                            <div
                              key={trigger.id}
                              onClick={() => navigate(`/chats/${entry.chat_id}/triggers`)}
                              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/chats/${entry.chat_id}/triggers`); } }}
                              role="button"
                              tabIndex={0}
                              className="p-2 bg-surface rounded-lg cursor-pointer flex items-center justify-between gap-2 min-w-0"
                            >
                              <div className="min-w-0 flex-1">
                                <div className="text-sm font-medium truncate">{trigger.key_phrase}</div>
                                <div className="text-xs text-hint">{formatDate(trigger.created_at)}</div>
                              </div>
                              <StatusBadge status={trigger.moderation_status} />
                            </div>
                          ))}
                          {hasMoreTriggers && (
                            <button
                              onClick={() => fetchChatTriggers(entry.chat_id, false)}
                              disabled={loadingTriggers}
                              className="w-full p-2 mt-1 text-link bg-transparent border-none cursor-pointer text-sm disabled:opacity-50"
                            >
                              {loadingTriggers ? 'Загрузка…' : 'Показать ещё'}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <div className="bg-danger-soft border border-danger/20 rounded-xl p-4 mb-4">
        <div className="flex items-center mb-3 text-danger">
          <Trash2 size={20} className="mr-2" />
          <h2 className="text-base font-bold m-0">Опасная зона</h2>
        </div>
        <p className="text-hint text-sm mb-3">
          Полностью удаляет пользователя и все связанные данные (сессии капчи, предупреждения, историю доверия, участие в чатах).
        </p>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="w-full py-2.5 px-4 rounded-xl font-medium bg-danger hover:opacity-90 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {deleting ? 'Удаление…' : 'Удалить пользователя'}
        </button>
      </div>
    </div>
  );
};

export default UserDetails;
