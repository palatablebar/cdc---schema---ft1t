import { useEffect, useRef, useState } from 'react';
import { runApi } from '../api/run';
import type { MergeRun } from '../types/models';

const TERMINAL = new Set(['succeeded', 'failed', 'canceled']);

/** 运行未终结时每 1.2s 轮询一次；终结即停，不在前端算任何结果。 */
export const useRunPolling = (initial: MergeRun | null, onUpdate?: (run: MergeRun) => void) => {
  const [run, setRun] = useState<MergeRun | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const updateRef = useRef(onUpdate);
  updateRef.current = onUpdate;

  useEffect(() => {
    setRun(initial);
  }, [initial]);

  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await runApi.get(run.id);
        if (cancelled) return;
        setRun(next);
        updateRef.current?.(next);
        if (TERMINAL.has(next.status)) return;
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '轮询失败');
        return;
      }
      timer.current = window.setTimeout(tick, 1200);
    };
    timer.current = window.setTimeout(tick, 900);
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [run?.id, run?.status]);

  return { run, error, isRunning: run ? !TERMINAL.has(run.status) : false };
};
