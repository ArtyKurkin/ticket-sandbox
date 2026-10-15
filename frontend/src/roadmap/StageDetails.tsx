import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Stage, StageStatus } from './types';
import { statusLabels } from './types';
import type { Journey } from './apiTypes';
import { canOpenAction, formatDate, notificationLabels } from './presentation';
import { positionCard, type Rect, type CardPosition } from './positioning';

export function StageDetails({ stage, status, surface, stationElements, onClose, journey, demonstration, baseHeight, onReserveSpace }: {
  stage: Stage; status: StageStatus; surface: HTMLDivElement | null;
  stationElements: ReadonlyMap<string, HTMLButtonElement>; onClose: (returnFocus?: boolean) => void;
  journey: Journey | null; demonstration: boolean; baseHeight: number; onReserveSpace: (height: number) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const [position, setPosition] = useState<CardPosition | null>(null);
  useLayoutEffect(() => {
    const card = ref.current, anchor = stationElements.get(stage.id);
    if (!card || !surface || !anchor) return;
    function update() {
      if (!card || !surface || !anchor) return;
      const canvas = surface.getBoundingClientRect();
      const relative = (element: HTMLElement): Rect => { const r = element.getBoundingClientRect(); return { left: r.left - canvas.left, top: r.top - canvas.top, width: r.width, height: r.height }; };
      const measured = card.getBoundingClientRect();
      const obstacles = [...stationElements.values()].flatMap(element => [...element.querySelectorAll<HTMLElement>('.rm-station-orbit, .rm-station-label')].map(relative));
      let next = positionCard({ width: canvas.width, height: baseHeight }, measured, relative(anchor), obstacles, stage.preferredSide);
      if (next.intersections > 0) {
        // Preserve route geometry; reserve scrollable space rather than cover a node.
        const extra = measured.height + 32;
        onReserveSpace(extra);
        next = positionCard({ width: canvas.width, height: baseHeight + extra }, measured, relative(anchor), obstacles, stage.preferredSide);
      } else onReserveSpace(0);
      setPosition(next);
    }
    update(); const observer = new ResizeObserver(update);
    observer.observe(surface); observer.observe(card);
    for (const element of stationElements.values()) observer.observe(element);
    return () => observer.disconnect();
  }, [stage, status, surface, stationElements, baseHeight, onReserveSpace]);
  useEffect(() => {
    if (position) ref.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [stage.id, position?.left, position?.top]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(true); };
    const outside = (event: PointerEvent) => {
      if (!(event.target instanceof Node) || ref.current?.contains(event.target)) return;
      if ([...stationElements.values()].some(element => element.contains(event.target as Node))) return;
      onClose(false);
    };
    document.addEventListener('keydown', onKey); document.addEventListener('pointerdown', outside);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', outside); };
  }, [onClose, stationElements]);
  const data = stage.data;
  const informational = status === 'coming_soon' || status === 'not_required';
  const latestPeriod = data.periods?.at(-1);
  const metrics = journey?.metrics ?? [];
  const speed = [...metrics].reverse().find(metric => metric.speed_tickets_per_hour !== null);
  const quality = [...metrics].reverse().find(metric => metric.quality_percent !== null);
  const working = stage.order >= 5 && stage.order <= 7;
  const outcome = data.evidence && 'outcome' in data.evidence ? data.evidence.outcome : null;
  const label = outcome === 'terminated' ? 'ИС прекращён' : outcome === 'insufficient_data' ? 'Результат отсутствует' : statusLabels[status];
  return <section ref={ref} id="rm-stage-details" role="dialog" aria-modal="false" aria-labelledby="rm-inspector-title"
    className={`rm-details rm-${status}`} data-intersections={position?.intersections}
    style={{ left: position?.left ?? 16, top: position?.top ?? 16, visibility: position ? 'visible' : 'hidden' }}>
    <header><span>ЭТАП {String(stage.order).padStart(2,'0')}</span><div><span className="rm-status-pill">{label}</span><button type="button" aria-label="Закрыть карточку этапа" onClick={() => onClose(true)}>×</button></div></header>
    <h2 id="rm-inspector-title">{data.title}</h2>
    {data.description && <p>{data.description}</p>}
    {status === 'not_required' && <p>Этот этап не входит в программу вашей адаптации.</p>}
    {journey?.state === 'not_started' && !informational && <p>Адаптация ещё не началась.</p>}
    {status === 'locked' && journey?.state !== 'not_started' && !outcome && <div className="rm-condition">Станция пока недоступна. Подтверждённое завершение отсутствует.</div>}
    {stage.id === 'training' && !informational && !demonstration && <p>{data.state === 'completed' ? 'Завершение обучения подтверждено наставником.' : 'Завершение обучения подтверждает наставник.'}</p>}
    {stage.id === 'sandbox' && !informational && !demonstration && <>
      {data.progress && <><div className="rm-detail-progress"><span>Технические задания</span><strong>{data.progress.completed}/{data.progress.total}</strong></div>
        {data.progress.total > 0 && <progress value={data.progress.completed} max={data.progress.total} aria-label="Текущий технический прогресс" />}</>}
      <p>{data.state === 'completed' ? 'Техническая часть завершена. Можно продолжать обучение и вернуться к ответам позже.' : 'Техническое завершение программы пока не зафиксировано.'}</p>
      {data.completion?.id !== null && data.completion?.completed_at && <p>Завершение сохранено {formatDate(data.completion.completed_at)} · {data.completion.total} заданий в снимке. Текущий каталог показан отдельно.</p>}
      {data.notifications?.some(item => item.count > 0) && <ul className="rm-notifications">{data.notifications.filter(item => item.count > 0).map(item => <li key={item.code}>{notificationLabels[item.code] ?? item.code}: <strong>{item.count}</strong></li>)}</ul>}
    </>}
    {working && !demonstration && <>
      {journey?.current_stage?.slug.replaceAll('-', '_') === stage.id && <p>Текущий рабочий этап</p>}
      {latestPeriod && <p>Начало: {formatDate(latestPeriod.started_at)}{latestPeriod.ended_at && ` · Окончание: ${formatDate(latestPeriod.ended_at)}`} · {latestPeriod.duration_days} дн.</p>}
      {(speed || quality || journey?.fixed_quality_percent !== null && journey?.fixed_quality_percent !== undefined) && <dl className="rm-real-metrics">
        {speed && <><dt>Скорость · неделя {speed.week_number}</dt><dd>{speed.speed_tickets_per_hour} тикетов/час</dd></>}
        {quality && <><dt>Качество · неделя {quality.week_number}</dt><dd>{quality.quality_percent}%</dd></>}
        {journey?.fixed_quality_percent !== null && journey?.fixed_quality_percent !== undefined && <><dt>Зафиксированное качество</dt><dd>{journey.fixed_quality_percent}%</dd></>}
      </dl>}
      {data.readiness && <div className="rm-readiness"><strong>{data.readiness.label}</strong>{data.readiness.reasons.map(reason => <p key={reason.code}>{reason.description}</p>)}</div>}
    </>}
    {stage.id === 'probation' && !demonstration && <p>{outcome === 'success' ? 'Испытательный срок успешно завершён.' : outcome === 'terminated' ? 'Испытательный срок прекращён. Успешное завершение не зафиксировано.' : outcome === 'insufficient_data' ? 'Подтверждённый исторический результат отсутствует.' : 'Адаптация продолжается.'}{journey?.completed_at && ` Дата: ${formatDate(journey.completed_at)}.`}</p>}
    {!demonstration && !informational && Boolean(data.data_quality?.length) && <p className="rm-evidence-note">В источнике есть неоднозначные исторические записи. Сохранённые результаты показаны отдельно.</p>}
    {!demonstration && !informational && data.evidence && 'completed' in data.evidence && !data.evidence.completed && status !== 'current' && <p className="rm-evidence-note">Недостаточно данных для подтверждения завершения.</p>}
    {demonstration && <p>Только демонстрация. Изменения не сохраняются.</p>}
    {!demonstration && !informational && data.action_notice && <p className="rm-evidence-note">{data.action_notice}</p>}
    {!demonstration && !informational && data.actions.filter(action => !action.enabled && action.reason).map(action => <p className="rm-evidence-note" key={action.code}>{action.reason}</p>)}
    {data.actions.filter(action => canOpenAction(data, action, demonstration)).map(action => <a key={action.code} className="rm-stage-action" href={action.url!} rel={action.external ? 'noopener noreferrer' : undefined}>{action.label} ›</a>)}
  </section>;
}
