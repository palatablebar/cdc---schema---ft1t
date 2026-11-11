import type { Board, CdcEvent, Stream } from '../types/models';
import type { Page } from '../types/api';
import { api } from './client';

export const streamApi = {
  board: () => api.get<Board>('/board'),
  list: () => api.get<{ items: Stream[] }>('/streams'),
  get: (id: string) => api.get<Stream>(`/streams/${id}`),
  events: (id: string, params: Record<string, string | number | boolean>) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '' && value !== undefined && value !== null) query.set(key, String(value));
    });
    return api.get<Page<CdcEvent>>(`/streams/${id}/events?${query.toString()}`);
  },
  arrivalStats: (id: string) =>
    api.get<{ arrival_inversions: number; duplicate_rows: number; event_rows: number }>(
      `/streams/${id}/arrival-stats`,
    ),
};
