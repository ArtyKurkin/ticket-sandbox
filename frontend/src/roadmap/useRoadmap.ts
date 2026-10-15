import { useEffect, useState } from 'react';
import { loadRoadmap, RoadmapError } from './api';
import type { RoadmapResponse } from './apiTypes';

export type LoadState = { status: 'loading' } | { status: 'success'; data: RoadmapResponse } | { status: 'error'; error: RoadmapError };
export function useRoadmap(url: string, allowedExternalHosts: readonly string[]) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    loadRoadmap(url, controller.signal, allowedExternalHosts).then(
      data => { if (!controller.signal.aborted) setState({ status: 'success', data }); },
      error => { if (!controller.signal.aborted) setState({ status: 'error', error: error instanceof RoadmapError ? error : new RoadmapError('server', 'Не удалось загрузить Roadmap.') }); },
    );
    return () => controller.abort();
  }, [url, revision, allowedExternalHosts]);
  return { state, retry: () => setRevision(value => value + 1) };
}
