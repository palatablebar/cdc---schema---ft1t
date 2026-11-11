import type { User } from '../types/models';
import { api } from './client';

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export const authApi = {
  login: (email: string, password: string) =>
    api.postAnonymous<LoginResponse>('/auth/login', { email, password }),
  me: () => api.get<User>('/auth/me'),
};
