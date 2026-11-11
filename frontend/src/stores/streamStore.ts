import { create } from 'zustand';
import { streamApi } from '../api/stream';
import { errorMessage } from '../utils/errorMessage';
import type { Board, Stream } from '../types/models';

interface StreamState {
  board: Board | null;
  loading: boolean;
  error: string | null;
  selectedStreamId: string | null;
  loadBoard: () => Promise<void>;
  selectStream: (id: string) => void;
  streams: () => Stream[];
}

export const useStreamStore = create<StreamState>((set, get) => ({
  board: null,
  loading: false,
  error: null,
  selectedStreamId: null,
  loadBoard: async () => {
    set({ loading: true, error: null });
    try {
      const board = await streamApi.board();
      const selected = get().selectedStreamId ?? board.streams[0]?.id ?? null;
      set({ board, loading: false, selectedStreamId: selected });
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
    }
  },
  selectStream: (id) => set({ selectedStreamId: id }),
  streams: () => get().board?.streams ?? [],
}));
