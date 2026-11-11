import type { SchemaDiff, SchemaVersion } from '../types/models';
import { api } from './client';

export interface VersionsResponse {
  items: SchemaVersion[];
  total: number;
  pairs: Array<{ left_version_id: string; right_version_id: string; label: string }>;
}

export const schemaApi = {
  versions: (streamId: string) => api.get<VersionsResponse>(`/streams/${streamId}/schema-versions`),
  diff: (leftVersionId: string, rightVersionId: string) =>
    api.post<SchemaDiff>('/schema/diff', {
      left_version_id: leftVersionId,
      right_version_id: rightVersionId,
    }),
};
