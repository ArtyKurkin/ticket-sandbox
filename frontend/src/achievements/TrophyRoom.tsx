import { useCallback, useEffect, useRef, useState } from 'react';
import { demoAchievements, demoUnlock } from './data';
import type { Achievement, Metal, MetalFilter, StatusFilter } from './types';
import { matchesFilters, metalLabels } from './types';
import { TrophyShell, type TrophyPageProps } from './TrophyShell';
import { TrophyStatsIcon } from './icons';
import { TrophyCard } from './TrophyCard';
import { TrophyFilters } from './TrophyFilters';
import { TrophyDetails } from './TrophyDetails';
import { TrophyUnlockToast } from './TrophyUnlockToast';

export function TrophyRoom({ profile }: { profile: TrophyPageProps }) {
  const [items, setItems] = useState<readonly Achievement[]>(demoAchievements);
  const [status, setStatus] = useState<StatusFilter>('all');
  const [metal, setMetal] = useState<MetalFilter>('all');
  const [selected, setSelected] = useState<Achievement | null>(null);
  const [toast, setToast] = useState<Achievement | null>(null);
  const [glowing, setGlowing] = useState<string | null>(null);
  const [toastSequence, setToastSequence] = useState(0);
  const demoRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const glowTimer = useRef<number | undefined>(undefined);
  const dismissToast = useCallback(() => setToast(null), []);
  useEffect(() => () => window.clearTimeout(glowTimer.current), []);
  const earned = items.filter(item => item.status === 'earned');
  const percent = Math.round(earned.length / items.length * 100);
  const visible = items.filter(item => matchesFilters(item, status, metal));

  function demonstrateUnlock() {
    // Temporary event fixture; only local React state changes. Reload restores it.
    const target = demoAchievements.find(item => item.id === demoUnlock.achievementId);
    if (!target) return;
    const unlocked: Achievement = { ...target, status: 'earned', progress: { percent: 100, label: demoUnlock.progressLabel }, earnedAt: new Intl.DateTimeFormat('ru-RU').format(new Date()) };
    if (!items.some(item => item.id === target.id && item.status === 'earned')) {
      setItems(current => current.map(item => item.id === target.id ? unlocked : item));
      setGlowing(target.id);
      window.clearTimeout(glowTimer.current);
      glowTimer.current = window.setTimeout(() => setGlowing(null), 2000);
    }
    setStatus('all'); setMetal('all');
    setToastSequence(current => current + 1);
    setToast(unlocked);
  }
  return <TrophyShell profile={profile}>
    <section className="tp-gallery" aria-label="Коллекция достижений">
      <div className="tp-heading"><div><div className="tp-title-line"><h1>Мои достижения</h1><span>ART SYSTEM 3.0</span></div><p>Коллекционные трофеи физического чекана за этапы программы онбординга Timeweb Cloud</p></div>
        <button type="button" ref={demoRef} className="tp-demo-button" onClick={demonstrateUnlock}><span aria-hidden="true">● ⊙</span> ▶ Демонстрация получения награды</button></div>
      <div className="tp-statistics"><div className="tp-stat-count"><span className="tp-cyan" aria-hidden="true"><TrophyStatsIcon /></span><span>Получено:</span><strong>{earned.length}</strong><span>/ {items.length}</span></div>
        <div className="tp-stat-metals">{(Object.keys(metalLabels) as Metal[]).map(value => <span className={`tp-${value}`} key={value}><i /><span>{metalLabels[value]}:</span><strong>{earned.filter(item => item.metal === value).length}</strong></span>)}</div>
        <div className="tp-room-progress"><span>ПРОГРЕСС КОМНАТЫ: <strong>{percent}%</strong></span><progress max="100" value={percent} aria-label="Прогресс комнаты" /></div>
      </div>
      <TrophyFilters items={items} status={status} metal={metal} onStatus={setStatus} onMetal={setMetal} />
      <div className="tp-trophy-grid">{visible.map(item => <TrophyCard key={item.id} achievement={item} glowing={glowing === item.id} onOpen={item => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setSelected(item); }} />)}</div>
      {visible.length === 0 && <p className="tp-empty" role="status">Нет достижений с выбранными фильтрами.</p>}
    </section>
    {selected && <TrophyDetails returnFocus={returnFocus.current} achievement={selected} onClose={() => setSelected(null)} />}
    {toast && <TrophyUnlockToast description={demoUnlock.description} key={toastSequence} achievement={toast} onDismiss={dismissToast} onOpen={() => { returnFocus.current = demoRef.current; setSelected(toast); setToast(null); }} />}
  </TrophyShell>;
}
