import type { MergeRun } from '../types/models';
import { api } from './client';

export const runApi = {
  list: (streamId?: string) =>
    api.get<{ items: MergeRun[]; total: number }>(
      `/runs${streamId ? `?stream_id=${encodeURIComponent(streamId)}` : ''}`,
    ),
  get: (id: string) => api.get<MergeRun>(`/runs/${id}`),
  create: (streamId: string, windowStart: number | null, windowEnd: number | null) =>
    api.post<MergeRun>('/runs', {
      stream_id: streamId,
      window_start_lsn: windowStart,
      window_end_lsn: windowEnd,
    }),
};
