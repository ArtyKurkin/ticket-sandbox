import { useEffect, useRef, useState } from 'react';
import type { Achievement, AchievementEvent, TrophyDetail } from './types';
import { cardStatus, conditionLabel, displayMetal, displayTitle, formatDate, isHidden, metalLabels } from './types';
import { loadDetail, mergeHistory, TrophyError } from './api';
import { TrophyMedallion } from './TrophyMedallion';

export function historyLabel(event: AchievementEvent): string {
  const label = (value: string | null) => value && Object.hasOwn(metalLabels, value) ? metalLabels[value as keyof typeof metalLabels] : value ?? '—';
  if (event.action === 'grant') return `Получена награда: ${label(event.to_tier)}`;
  if (event.action === 'upgrade') return `Повышение: ${label(event.from_tier)} → ${label(event.to_tier)}`;
  if (event.action === 'revoke') return 'Награда отозвана';
  return 'Доказательство требует проверки';
}
export function History({ events }: { events: readonly AchievementEvent[] }) {
  return <ol className="tp-history-list">{events.map(event => <li key={event.id} data-event-id={event.id}>
    <time dateTime={event.recorded_at}>{formatDate(event.recorded_at)}</time><strong>{historyLabel(event)}</strong>
    {event.manual && <span>Ручное решение наставника</span>}
    {event.source === 'roadmap_confirmation' && <span>Обучение подтверждено наставником</span>}
    {event.reason && <p>{event.reason}</p>}
  </li>)}</ol>;
}
export function TrophyDetails({ achievement, apiUrl, demonstration = false, onClose, returnFocus, loginUrl }: {
  achievement: Achievement; apiUrl: string; demonstration?: boolean; onClose: () => void; returnFocus: HTMLElement | null; loginUrl: string;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const pageController = useRef<AbortController | null>(null);
  const [detail, setDetail] = useState<TrophyDetail | null>(demonstration ? { achievement, history: [], nextCursor: null } : null);
  const [error, setError] = useState<TrophyError | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loadingPage, setLoadingPage] = useState(false);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = returnFocus ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    dialog?.showModal(); closeRef.current?.focus();
    return () => { dialog?.close(); if (previousFocus?.isConnected) previousFocus.focus(); pageController.current?.abort(); };
  }, []);
  useEffect(() => {
    if (demonstration) return;
    const controller = new AbortController();
    setDetail(null); setError(null);
    loadDetail(apiUrl, achievement.id, null, controller.signal).then(result => {
      if (!controller.signal.aborted) setDetail(result);
    }).catch(error => { if (!controller.signal.aborted) setError(error instanceof TrophyError ? error : new TrophyError('contract', 'Не удалось прочитать историю.')); });
    return () => controller.abort();
  }, [apiUrl, achievement.id, attempt, demonstration]);
  async function nextPage() {
    if (!detail?.nextCursor || loadingPage || demonstration) return;
    pageController.current?.abort();
    const controller = new AbortController(); pageController.current = controller;
    setLoadingPage(true); setError(null);
    try {
      const page = await loadDetail(apiUrl, achievement.id, detail.nextCursor, controller.signal);
      if (!controller.signal.aborted) setDetail(previous => previous ? {
        ...page, history: isHidden(page.achievement) ? [] : mergeHistory(previous.history, page.history),
      } : page);
    } catch (error) {
      if (!controller.signal.aborted) {
        const failure = error instanceof TrophyError ? error : new TrophyError('network', 'Не удалось загрузить историю.');
        if (['unauthorized', 'forbidden', 'not_found'].includes(failure.kind)) setDetail(null);
        setError(failure);
      }
    } finally { if (!controller.signal.aborted) setLoadingPage(false); }
  }
  const current = detail?.achievement ?? achievement;
  const hidden = isHidden(current), metal = displayMetal(current);
  const condition = current.supportedTiers.find(t => t.code === current.highestTier?.code)?.criterion;
  return <dialog ref={dialogRef} className={`tp-details tp-${hidden ? 'secret' : metal ?? 'neutral'}`}
    aria-labelledby="tp-details-title" aria-describedby="tp-details-description"
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select, input, [tabindex="0"]');
      if (!controls?.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
    }}>
    <button type="button" ref={closeRef} className="tp-close" aria-label="Закрыть подробности" onClick={onClose}>×</button>
    <div className="tp-detail-art"><TrophyMedallion achievement={current} /></div>
    <div className="tp-detail-heading"><span className="tp-metal-badge">{hidden ? 'Скрыто' : metal ? metalLabels[metal] : 'Уровень не получен'}</span>
      {!hidden && current.earnedAt && <span>Первая выдача: {formatDate(current.earnedAt)}</span>}</div>
    <h2 id="tp-details-title">{displayTitle(current)}</h2>
    <p id="tp-details-description">{hidden ? 'Подробности станут доступны после получения награды.' : current.description}</p>
    {!detail && !error && <p role="status" className="tp-request-state">Загружаем подробности и историю…</p>}
    {error && <div role="alert" className="tp-request-state"><p>{error.message}</p>
      {error.kind === 'unauthorized' && <a href={loginUrl}>Войти</a>}
      <button type="button" onClick={() => { if (detail) void nextPage(); else setAttempt(a => a + 1); }}>Повторить загрузку</button></div>}
    {detail && <>
      <div className="tp-detail-progress"><span className="tp-muted">{cardStatus(current)}{!hidden && current.manualGrant && ' • Ручная выдача наставником'}</span>
        {!hidden && current.dataQuality === 'disputed' && <p className="tp-disputed">Результат требует проверки. Уровень награды сохранён.</p>}
        {!hidden && condition && <><p>Условие текущего уровня:</p><strong>{conditionLabel(condition)}</strong></>}
        {!hidden && current.progress && <><p>{current.progress.label}</p><progress max="100" value={current.progress.percent} aria-label="Прогресс достижения" /></>}
      </div>
      {!hidden && <section className="tp-tiers" aria-label="Уровни награды"><h3>Уровни</h3><ul>{current.supportedTiers.map(tier => <li key={tier.code}>
        <span className={`tp-${tier.rarity}`}>{metalLabels[tier.rarity]}</span><span>{conditionLabel(tier.criterion)}</span>
      </li>)}</ul></section>}
      {!hidden && <section className="tp-history" aria-label="История награды"><h3>История</h3>
        {demonstration ? <p>Демонстрация: настоящие выдачи и история не меняются.</p> : detail.history.length ? <History events={detail.history} /> : <p>Выдач пока нет.</p>}
        {detail.nextCursor && <button type="button" disabled={loadingPage} onClick={() => void nextPage()}>{loadingPage ? 'Загружаем…' : 'Показать ещё'}</button>}
      </section>}
    </>}
    <div className="tp-detail-footer"><button type="button" onClick={onClose}>Закрыть</button></div>
  </dialog>;
}
