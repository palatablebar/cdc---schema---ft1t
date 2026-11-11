import { useCallback, useState } from 'react';
import type { CdcOp } from '../types/models';

export interface EventFilterState {
  op: CdcOp | '';
  onlyRejected: boolean;
  order: 'lsn' | 'arrival' | 'lsn_desc';
  page: number;
  limit: number;
}

const DEFAULTS: EventFilterState = { op: '', onlyRejected: false, order: 'lsn', page: 0, limit: 40 };

/** 事件列表筛选状态：改任意筛选条件自动回到第一页。 */
export const useEventFilters = () => {
  const [filters, setFilters] = useState<EventFilterState>(DEFAULTS);

  const setOp = useCallback((op: CdcOp | '') => setFilters((prev) => ({ ...prev, op, page: 0 })), []);
  const toggleRejected = useCallback(
    () => setFilters((prev) => ({ ...prev, onlyRejected: !prev.onlyRejected, page: 0 })),
    [],
  );
  const setOrder = useCallback(
    (order: EventFilterState['order']) => setFilters((prev) => ({ ...prev, order, page: 0 })),
    [],
  );
  const setPage = useCallback((page: number) => setFilters((prev) => ({ ...prev, page })), []);
  const reset = useCallback(() => setFilters(DEFAULTS), []);

  return { filters, setOp, toggleRejected, setOrder, setPage, reset };
};
