import type { EventDiff } from '../types/models';
import { api } from './client';

export const eventApi = {
  diff: (eventId: string) => api.get<EventDiff>(`/events/${eventId}`),
};
