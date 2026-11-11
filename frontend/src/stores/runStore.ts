import { create } from 'zustand';
import { runApi } from '../api/run';
import { errorMessage } from '../utils/errorMessage';
import type { MergeRun } from '../types/models';

interface RunState {
  runs: MergeRun[];
  current: MergeRun | null;
  loading: boolean;
  starting: boolean;
  error: string | null;
  loadRuns: (streamId?: string) => Promise<void>;
  loadRun: (id: string) => Promise<MergeRun | null>;
  startRun: (streamId: string, windowStart: number | null, windowEnd: number | null) => Promise<MergeRun | null>;
  clearError: () => void;
}

export const useRunStore = create<RunState>((set) => ({
  runs: [],
  current: null,
  loading: false,
  starting: false,
  error: null,
  loadRuns: async (streamId) => {
    set({ loading: true, error: null });
    try {
      const response = await runApi.list(streamId);
      set({ runs: response.items, loading: false });
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
    }
  },
  loadRun: async (id) => {
    try {
      const run = await runApi.get(id);
      set({ current: run });
      return run;
    } catch (error) {
      set({ error: errorMessage(error) });
      return null;
    }
  },
  startRun: async (streamId, windowStart, windowEnd) => {
    set({ starting: true, error: null });
    try {
      const run = await runApi.create(streamId, windowStart, windowEnd);
      set((state) => ({ starting: false, current: run, runs: [run, ...state.runs] }));
      return run;
    } catch (error) {
      set({ starting: false, error: errorMessage(error) });
      return null;
    }
  },
  clearError: () => set({ error: null }),
}));
