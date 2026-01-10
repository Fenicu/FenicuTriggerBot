export interface Pagination {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: Pagination;
}

export interface User {
  id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_id?: string;
  is_bot_moderator: boolean;
  is_trusted: boolean;
  created_at: string;
}

export interface Chat {
  id: number;
  title?: string;
  username?: string;
  type?: string;
  description?: string;
  invite_link?: string;
  photo_id?: string;
  admins_only_add: boolean;
  language_code: string;
  warn_limit: number;
  warn_punishment: string;
  warn_duration: number;
  is_trusted: boolean;
  is_active: boolean;
  created_at: string;
  is_banned: boolean;
  ban_reason?: string;
  triggers_count: number;
}

export interface UserChat {
  chat: Chat;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatUser {
  user: User;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface UpdateUserRoleRequest {
  is_trusted?: boolean;
  is_bot_moderator?: boolean;
}

export interface BanChatRequest {
  reason: string;
}

export interface SendMessageRequest {
  text: string;
}

export interface Trigger {
  id: number;
  chat_id: number;
  key_phrase: string;
  content: any;
  match_type: string;
  is_case_sensitive: boolean;
  access_level: string;
  usage_count: number;
  created_by: number;
  moderation_status: string;
  moderation_reason?: string;
}
