import { useCallback, useRef, useState } from 'react';
import type { Achievement, Metal, MetalFilter, StatusFilter, TrophyCollection } from './types';
import { matchesFilters, metalLabels } from './types';
import { TrophyShell, type TrophyPageProps } from './TrophyShell';
import { TrophyStatsIcon } from './icons';
import { TrophyCard } from './TrophyCard';
import { TrophyDetails } from './TrophyDetails';
import { TrophyFilters } from './TrophyFilters';
import { TrophyUnlockToast } from './TrophyUnlockToast';
import { useTrophies } from './useTrophies';

export function TrophyRoom({ profile }: { profile: TrophyPageProps }) {
  const { state, retry } = useTrophies(profile.achievementsApiUrl);
  const [demo, setDemo] = useState<TrophyCollection | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>('all');
  const [metal, setMetal] = useState<MetalFilter>('all');
  const [category, setCategory] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<Achievement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const demonstration = profile.canDemo === true && demo !== null;
  const collection = demonstration ? demo : state.status === 'ready' ? state.data : null;
  const items = collection?.items ?? [];
  const selected = items.find(a => a.id === selectedId) ?? null;
  const visible = items.filter(a => matchesFilters(a, status, metal, category));
  function resetSelection() { setSelectedId(null); setToast(null); setStatus('all'); setMetal('all'); setCategory('all'); setDemoError(null); }
  async function enterDemo() {
    if (profile.canDemo !== true || demoLoading) return;
    setDemoLoading(true);
    try { const module = await import('./demonstration'); resetSelection(); setDemo(module.demoCollection()); }
    catch { setDemoError('Не удалось открыть демонстрацию. Попробуйте снова.'); }
    finally { setDemoLoading(false); }
  }
  async function unlockDemo() {
    if (profile.canDemo !== true || !demonstration || !demo) return;
    try {
      const module = await import('./demonstration');
      const next = module.demoUnlock(demo.items, profile.canDemo === true);
      setDemo({ ...demo, items: next, stats: module.demoStats(next) });
      if (demo.items.find(a => a.id === 'demo-3')?.status !== 'earned') setToast(next.find(a => a.id === 'demo-3') ?? null);
      setStatus('all'); setMetal('all'); setCategory('all');
    } catch { setDemoError('Не удалось показать демонстрацию. Попробуйте снова.'); }
  }
  return <TrophyShell profile={profile}>
    <section className="tp-gallery" aria-label="Коллекция достижений" data-mode={demonstration ? 'demo' : 'real'}>
      <div className="tp-heading"><div><div className="tp-title-line"><h1>Мои достижения</h1><span>ART SYSTEM 3.0</span></div><p>Коллекционные трофеи за этапы обучения и результаты работы</p></div>
        <div className="tp-room-actions">
          {!demonstration && <button type="button" className="tp-demo-button" disabled={state.status === 'loading'} onClick={() => { setSelectedId(null); retry(); }}>Обновить</button>}
          {profile.canDemo === true && <button type="button" className="tp-demo-button" disabled={demoLoading} onClick={() => {
            if (demonstration) { resetSelection(); setDemo(null); } else void enterDemo();
          }}>{demonstration ? 'К реальным достижениям' : demoLoading ? 'Открываем демонстрацию…' : 'Демонстрация'}</button>}
        </div>
      </div>
      {profile.canDemo === true && demoError && <p className="tp-request-state" role="alert">{demoError}</p>}
      {demonstration && <div className="tp-demo-notice" role="status"><strong>Демонстрационный режим</strong><span>Показаны примеры. Настоящие достижения и история не меняются.</span>
        <button type="button" className="tp-demo-button" onClick={() => void unlockDemo()}>Показать получение награды</button></div>}
      {!demonstration && state.status === 'loading' && <p className="tp-request-state" role="status">Загружаем достижения…</p>}
      {!demonstration && state.status === 'error' && <div className="tp-request-state" role="alert"><p>{state.error.message}</p>
        {state.error.kind === 'unauthorized' && <a href={profile.loginUrl}>Войти</a>}<button type="button" onClick={retry}>Повторить загрузку</button></div>}
      {collection && <>
        <div className="tp-statistics"><div className="tp-stat-count"><span className="tp-cyan" aria-hidden="true"><TrophyStatsIcon /></span><span>Получено:</span><strong>{collection.stats.earned}</strong><span>/ {collection.stats.applicable_total}</span></div>
          <div className="tp-stat-metals">{(Object.keys(metalLabels) as Metal[]).map(value => <span className={`tp-${value}`} key={value}><i /><span>{metalLabels[value]}:</span><strong>{collection.stats.rarities[value]}</strong></span>)}</div>
        </div>
        {!demonstration && collection.pendingEvents > 0 && <p className="tp-pending" role="status">Некоторые результаты ещё обрабатываются. Обновите коллекцию немного позже.</p>}
        <TrophyFilters items={items} status={status} metal={metal} category={category} onStatus={setStatus} onMetal={setMetal} onCategory={setCategory} />
        <div className="tp-trophy-grid">{visible.map(a => <TrophyCard key={a.id} achievement={a} glowing={toast?.id === a.id} onOpen={item => {
          returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setSelectedId(item.id);
        }} />)}</div>
        {items.length === 0 ? <p className="tp-empty">Каталог достижений пока пуст.</p> : visible.length === 0 && <p className="tp-empty">Нет достижений с выбранными фильтрами.</p>}
      </>}
      {selected && <TrophyDetails key={`${selected.id}:${selected.revision}:${selected.status}`} achievement={selected} apiUrl={profile.achievementsApiUrl}
        loginUrl={profile.loginUrl} demonstration={demonstration} returnFocus={returnFocus.current} onClose={() => setSelectedId(null)} />}
      {demonstration && toast && <TrophyUnlockToast achievement={toast} demonstration description="Пример анимации. Награда не сохраняется."
        onDismiss={dismissToast} onOpen={() => {
          returnFocus.current = document.querySelector<HTMLButtonElement>('.tp-demo-notice button');
          setSelectedId(toast.id); setToast(null);
        }} />}
    </section>
  </TrophyShell>;
}
