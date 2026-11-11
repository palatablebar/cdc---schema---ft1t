import type { Page } from '../types/api';
import type { ReplayResult, RejectedEvent } from '../types/models';
import { api } from './client';

export const rejectedApi = {
  list: (params: { stream_id?: string; status?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value));
    });
    return api.get<Page<RejectedEvent>>(`/rejected?${query.toString()}`);
  },
  replay: (id: string) => api.post<ReplayResult>(`/rejected/${id}/replay`),
  dismiss: (id: string) => api.post<RejectedEvent>(`/rejected/${id}/dismiss`),
};
