import { useCallback, useEffect, useState } from 'react';
import type { TrophyCollection } from './types';
import { loadCollection, TrophyError } from './api';

export type CollectionState = { status: 'loading' } | { status: 'ready'; data: TrophyCollection } | { status: 'error'; error: TrophyError };
export function useTrophies(url: string) {
  const [state, setState] = useState<CollectionState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => { setState({ status: 'loading' }); setAttempt(a => a + 1); }, []);
  useEffect(() => {
    const controller = new AbortController();
    loadCollection(url, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ status: 'ready', data });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ status: 'error', error: error instanceof TrophyError ? error : new TrophyError('contract', 'Не удалось загрузить достижения.') });
    });
    return () => controller.abort();
  }, [url, attempt]);
  return { state, retry };
}
