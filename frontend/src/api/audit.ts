import type { Page } from '../types/api';
import type { AuditLog } from '../types/models';
import { api } from './client';

export const auditApi = {
  list: (limit = 50) => api.get<Page<AuditLog>>(`/audit?limit=${limit}`),
};
