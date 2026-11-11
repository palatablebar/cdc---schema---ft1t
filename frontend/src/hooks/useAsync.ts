import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage } from '../utils/errorMessage';

/** 极简异步加载 hook：带依赖数组、卸载保护、手动 reload。 */
export const useAsync = <T,>(loader: () => Promise<T>, deps: unknown[]) => {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const value = await loaderRef.current();
      if (mounted.current) setData(value);
    } catch (err) {
      if (mounted.current) setError(errorMessage(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void run();
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, reload: run, setData };
};
