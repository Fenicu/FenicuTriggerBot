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
